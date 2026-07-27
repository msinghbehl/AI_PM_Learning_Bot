"""Source fetcher: reads local files, fetches URLs, extracts PDF text,
follows one-hop links, and fetches GitHub READMEs via gh api.

Per spec §2.1: accepts .md/.txt (read directly), .url (fetch first line),
.pdf (extract text), GitHub repo URLs (gh api README), bare URLs (requests).
One-hop link following: extract links from fetched content, fetch each, no recursion.
"""
from __future__ import annotations

import base64
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import requests

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


@dataclass
class FetchResult:
    """Result of fetching a source — success or failure with error message."""
    success: bool
    content: str = ""
    url: str | None = None
    source_path: str | None = None
    error: str | None = None
    one_hop_links: list[str] = field(default_factory=list)


def read_local_file(path: Path | str) -> FetchResult:
    """Read a local .md, .txt, or .url file.

    For .url files, the first line is the URL; returns a FetchResult with the
    url set so the caller can fetch it. For .md/.txt, returns the content directly.
    """
    path = Path(path)
    if not path.exists():
        return FetchResult(success=False, error=f"File not found: {path}", source_path=str(path))

    text = path.read_text(encoding="utf-8")

    if path.suffix == ".url":
        lines = text.strip().splitlines()
        if not lines or not _looks_like_url(lines[0]):
            return FetchResult(
                success=False,
                error="couldn't fetch, paste it — .url file has no valid URL on first line",
                source_path=str(path),
            )
        return FetchResult(
            success=True,
            content=text,
            url=lines[0],
            source_path=str(path),
        )

    return FetchResult(success=True, content=text, source_path=str(path))


def _looks_like_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def fetch_url(url: str, timeout: int = 30, max_bytes: int = 10_000_000) -> FetchResult:
    """Fetch a URL with requests (no JS, no auth). If PDF, extract text.

    Per spec §2.1: if 401/403/JS-required, log "couldn't fetch, paste it" and skip.
    Caps response size at max_bytes (default 10MB) to avoid OOM on hostile URLs.
    """
    try:
        resp = requests.get(
            url, timeout=timeout, stream=True,
            headers={"User-Agent": "ingestion-agent/0.1"},
        )
    except requests.RequestException as e:
        return FetchResult(success=False, url=url, error=f"couldn't fetch, paste it — {e}")

    if resp.status_code in (401, 403):
        return FetchResult(success=False, url=url, error="couldn't fetch, paste it — auth required")
    if resp.status_code >= 400:
        return FetchResult(success=False, url=url, error=f"couldn't fetch, paste it — HTTP {resp.status_code}")

    # Check content-length and reject oversized responses (CRITICAL fix)
    content_length = resp.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        return FetchResult(success=False, url=url, error="couldn't fetch — response too large")

    content_type = resp.headers.get("content-type", "")

    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        content_bytes = b""
        for chunk in resp.iter_content(chunk_size=8192):
            content_bytes += chunk
            if len(content_bytes) > max_bytes:
                return FetchResult(success=False, url=url, error="couldn't fetch — PDF too large")
        text = extract_pdf_text(content_bytes)
        return FetchResult(success=True, content=text, url=url)

    text_content = ""
    for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
        if chunk:
            # decode_unicode=True should give str, but handle bytes just in case
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", errors="replace")
            text_content += chunk
            if len(text_content) > max_bytes:
                return FetchResult(success=False, url=url, error="couldn't fetch — response too large")

    return FetchResult(success=True, content=text_content, url=url)


def extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    if PdfReader is None:
        return "(pypdf not installed — cannot extract PDF text)"
    import io
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_links(text: str) -> list[str]:
    """Extract hyperlinks from text — markdown links and bare URLs.

    Per spec §2.1 one-hop following: extract [text](url) and bare URLs.
    Deduplicates; ignores anchor-only links (#section).
    """
    links: list[str] = []

    # Markdown links: [text](url)
    for match in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text):
        url = match.group(2).strip()
        if url.startswith(("http://", "https://")):
            links.append(url)

    # Bare URLs
    for match in re.finditer(r"(?<![\(\[])(https?://[^\s\)\]]+)", text):
        url = match.group(1).rstrip(".,;:")
        links.append(url)

    # Deduplicate, preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def fetch_github_readme(owner: str, repo: str) -> FetchResult:
    """Fetch a GitHub repo README via `gh api repos/<owner>/<repo>/readme`.

    Per spec §2.1: returns base64; decode. Do NOT clone.
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/readme", "--jq", ".content"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return FetchResult(success=False, error=f"couldn't fetch README — gh api failed: {e}")

    if result.returncode != 0:
        return FetchResult(success=False, error=f"couldn't fetch README — {result.stderr.strip()}")

    try:
        decoded = base64.b64decode(result.stdout.strip()).decode("utf-8")
    except Exception as e:
        return FetchResult(success=False, error=f"couldn't decode README — {e}")

    return FetchResult(success=True, content=decoded)


_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/?$")


def read_source(source: str) -> FetchResult:
    """Dispatch to the right reader based on source type.

    - Local .md/.txt → read_local_file
    - Local .url → read_local_file (gets URL), then fetch_url
    - GitHub repo URL → fetch_github_readme
    - Bare URL → fetch_url
    """
    # Local file path
    if not source.startswith(("http://", "https://")) and not source.startswith("pasted:"):
        path = Path(source)
        result = read_local_file(path)

        # .url files: the content has the URL; fetch it
        if result.success and result.url:
            fetched = fetch_url(result.url)
            # Preserve source_path from the .url file for provenance
            fetched.source_path = result.source_path
            return fetched
        return result

    # GitHub repo URL
    github_match = _GITHUB_URL_RE.match(source)
    if github_match:
        owner, repo = github_match.group(1), github_match.group(2)
        return fetch_github_readme(owner, repo)

    # Bare URL
    return fetch_url(source)
