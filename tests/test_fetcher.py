"""Tests for the fetcher module.

Tests cover: reading local files (.md/.txt), parsing .url files, fetching URLs
(mocked), PDF extraction (mocked), one-hop link extraction, and GitHub README
fetching (mocked gh api).
"""
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion_agent.fetcher import (
    FetchResult,
    extract_links,
    fetch_github_readme,
    fetch_url,
    read_local_file,
    read_source,
)


class TestReadLocalFile:
    def test_reads_markdown_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome content here.")
        result = read_local_file(f)
        assert result.success is True
        assert "Some content here." in result.content
        assert result.source_path == str(f)

    def test_reads_text_file(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("plain text notes")
        result = read_local_file(f)
        assert result.success is True
        assert result.content == "plain text notes"

    def test_missing_file_returns_failure(self, tmp_path):
        result = read_local_file(tmp_path / "nonexistent.md")
        assert result.success is False
        assert "not found" in result.error.lower()


class TestReadUrlFile:
    def test_url_file_first_line_is_url(self, tmp_path):
        f = tmp_path / "source.url"
        f.write_text("https://example.com/article\n\nSome context notes.")
        result = read_local_file(f)
        assert result.success is True
        assert result.url == "https://example.com/article"
        assert "Some context notes." in result.content

    def test_url_file_without_url_returns_failure(self, tmp_path):
        f = tmp_path / "bad.url"
        f.write_text("not a url, just text")
        result = read_local_file(f)
        assert result.success is False


class TestFetchUrl:
    @patch("ingestion_agent.fetcher.requests.get")
    def test_fetches_html_content(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Article content</body></html>"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.iter_content.return_value = [
            b"<html><body>Article content</body></html>"]
        mock_get.return_value = mock_resp

        result = fetch_url("https://example.com/article")
        assert result.success is True
        assert "Article content" in result.content

    @patch("ingestion_agent.fetcher.requests.get")
    def test_403_returns_failure_with_skip_message(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        result = fetch_url("https://example.com/protected")
        assert result.success is False
        assert "couldn't fetch" in result.error.lower()

    @patch("ingestion_agent.fetcher.requests.get")
    def test_pdf_url_downloads_and_extracts(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.iter_content.return_value = [b"%PDF-1.4 fake pdf"]
        mock_get.return_value = mock_resp

        with patch("ingestion_agent.fetcher.extract_pdf_text", return_value="Extracted PDF text"):
            result = fetch_url("https://example.com/paper.pdf")
            assert result.success is True
            assert result.content == "Extracted PDF text"

    @patch("ingestion_agent.fetcher.requests.get")
    def test_oversized_response_rejected(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html",
                             "content-length": "20000000"}
        mock_get.return_value = mock_resp

        result = fetch_url("https://example.com/huge")
        assert result.success is False
        assert "too large" in result.error.lower()


class TestExtractLinks:
    def test_extracts_markdown_links(self):
        text = "See [this blog](https://example.com/blog) for more."
        links = extract_links(text)
        assert "https://example.com/blog" in links

    def test_extracts_bare_urls(self):
        text = "Check https://example.com/article for details."
        links = extract_links(text)
        assert "https://example.com/article" in links

    def test_deduplicates_links(self):
        text = "[link](https://example.com) and https://example.com again"
        links = extract_links(text)
        assert links.count("https://example.com") == 1

    def test_no_links_returns_empty(self):
        links = extract_links("just plain text, no links")
        assert links == []

    def test_ignores_anchor_only_links(self):
        text = "[section](#section-1) internal link"
        links = extract_links(text)
        assert links == []

    def test_strips_html_attribute_artifacts(self):
        """Trailing \", >, /> from HTML attributes should be stripped."""
        text = 'href="https://example.com/page"> and href="https://example.com/other"/>'
        links = extract_links(text)
        assert "https://example.com/page" in links
        assert "https://example.com/other" in links
        # No URL should have trailing artifacts
        for link in links:
            assert not link.endswith((">", '"', "/", "'"))

    def test_skips_non_content_extensions(self):
        """CSS, JS, image, and font URLs should be filtered out."""
        text = """
        [style](https://example.com/assets/main.css)
        [script](https://example.com/assets/app.js)
        [image](https://example.com/img/photo.jpg)
        [icon](https://example.com/favicon.ico)
        [font](https://example.com/fonts/inter.woff2)
        [svg](https://example.com/logo.svg)
        [content](https://example.com/blog/post)
        """
        links = extract_links(text)
        assert "https://example.com/blog/post" in links
        assert not any(".css" in link for link in links)
        assert not any(".js" in link for link in links)
        assert not any(".jpg" in link for link in links)
        assert not any(".ico" in link for link in links)
        assert not any(".woff2" in link for link in links)
        assert not any(".svg" in link for link in links)

    def test_skips_asset_hosts(self):
        """Known CDN/infrastructure hosts should be filtered out."""
        text = """
        [avatar](https://avatars.githubusercontent.com/u/123)
        [asset](https://github.githubassets.com/assets/main.css)
        [fonts](https://fonts.googleapis.com/css?family=Inter)
        [gstatic](https://fonts.gstatic.com/s/inter/v12.woff2)
        [cdn](https://cdn.prod.website-files.com/5f8b/image.jpg)
        [s3](https://github-cloud.s3.amazonaws.com/user-attachments/123.png)
        [content](https://example.com/article)
        """
        links = extract_links(text)
        assert "https://example.com/article" in links
        assert not any("avatars.githubusercontent" in link for link in links)
        assert not any("githubassets" in link for link in links)
        assert not any("fonts.googleapis" in link for link in links)
        assert not any("fonts.gstatic" in link for link in links)
        assert not any("cdn.prod.website-files" in link for link in links)
        assert not any("github-cloud.s3" in link for link in links)

    def test_skips_hreflang_alternates(self):
        """Localized mirrors should be skipped when canonical is present."""
        text = """
        [canonical](https://openai.com/index/gpt-4-research/)
        [arabic](https://openai.com/ar/index/gpt-4-research/)
        [bulgarian](https://openai.com/bg-BG/index/gpt-4-research/)
        [french](https://openai.com/fr/index/gpt-4-research/)
        """
        links = extract_links(text)
        assert "https://openai.com/index/gpt-4-research/" in links
        # hreflang alternates should be filtered out
        assert not any("/ar/" in link for link in links)
        assert not any("/bg-BG/" in link for link in links)
        assert not any("/fr/" in link for link in links)


class TestFetchGithubReadme:
    @patch("ingestion_agent.fetcher.subprocess.run")
    def test_fetches_and_decodes_readme(self, mock_run):
        readme_content = "# Repo Title\n\nDescription."
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=base64.b64encode(readme_content.encode()).decode(),
        )

        result = fetch_github_readme("owner", "repo")
        assert result.success is True
        assert "Repo Title" in result.content

    @patch("ingestion_agent.fetcher.subprocess.run")
    def test_gh_failure_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="HTTP 404: Not Found",
        )

        result = fetch_github_readme("owner", "nonexistent")
        assert result.success is False


class TestReadSource:
    def test_dispatches_to_local_file_for_md(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Doc\nContent")
        result = read_source(str(f))
        assert result.success is True
        assert "Content" in result.content

    def test_dispatches_to_url_file(self, tmp_path):
        f = tmp_path / "source.url"
        f.write_text("https://example.com/page\n\nContext.")
        with patch("ingestion_agent.fetcher.fetch_url") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                success=True, content="Fetched page content", url="https://example.com/page"
            )
            result = read_source(str(f))
            assert result.success is True
            mock_fetch.assert_called_once_with("https://example.com/page")

    def test_dispatches_to_github_url(self):
        with patch("ingestion_agent.fetcher.fetch_github_readme") as mock_gh:
            mock_gh.return_value = FetchResult(
                success=True, content="# Repo README"
            )
            result = read_source("https://github.com/owner/repo")
            assert result.success is True
            mock_gh.assert_called_once_with("owner", "repo")

    @patch("ingestion_agent.fetcher.fetch_url")
    def test_dispatches_to_bare_url(self, mock_fetch):
        mock_fetch.return_value = FetchResult(
            success=True, content="Web content", url="https://example.com"
        )
        result = read_source("https://example.com/article")
        assert result.success is True
