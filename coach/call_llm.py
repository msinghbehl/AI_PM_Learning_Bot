"""Provider-agnostic call_llm wrapper — routes to Anthropic direct.

Per #5: Haiku 4.5 cheap / Sonnet 4.6 strong / Opus 4.5 per-call escalation,
behind a single interface so a future provider switch is a wrapper edit.
Reflexive-reprompt on schema violations (ported from Task_IQ classifier.py).
Tenacity retry on transient API failures. Every call is logged to the cost
ledger and gated by the fallback ladder.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from coach.config import ModelName
from coach.cost_ledger import CapStatus, CostLedger

log = logging.getLogger("coach.call_llm")

_MAX_RETRIES = 3


class LLMError(RuntimeError):
    """Raised when the model cannot produce a usable response after retries."""


class SchemaError(LLMError):
    """Raised when structured output fails schema validation after reflexive retry."""


class LLMClient(Protocol):
    """Abstract LLM boundary — tests inject a fake; production uses Anthropic."""

    def complete(self, model: ModelName, system: str, messages: list[dict[str, str]],
                 max_tokens: int) -> tuple[str, int, int, int]:
        """Return (text, input_tokens, output_tokens, cache_read_tokens)."""
        ...


@dataclass(frozen=True)
class LLMResponse:
    """One LLM call result."""

    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    model: ModelName


class AnthropicClient:
    """Production LLM client — Anthropic direct."""

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    @retry(stop=stop_after_attempt(_MAX_RETRIES), wait=wait_exponential(min=1, max=8), reraise=True)
    def complete(self, model: ModelName, system: str, messages: list[dict[str, str]],
                 max_tokens: int) -> tuple[str, int, int, int]:
        resp = self._client.messages.create(
            model=model.value,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        text = resp.content[0].text if resp.content else ""
        return (
            text,
            resp.usage.input_tokens,
            resp.usage.output_tokens,
            getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        )


def _strip_fences(text: str) -> str:
    """Tolerate accidental markdown fences around JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return t


class CallLLM:
    """The provider-agnostic wrapper.

    Routes to the right model, applies the fallback ladder, logs every call to
    the cost ledger, and does reflexive-reprompt on schema-violating structured
    outputs.
    """

    def __init__(self, client: LLMClient, ledger: CostLedger) -> None:
        self._client = client
        self._ledger = ledger

    def _resolve_model(self, model: ModelName, purpose: str, caps: CapStatus) -> ModelName:
        """Apply the fallback ladder: economy mode downgrades Sonnet→Haiku.

        The critic is never downgraded (grading trust floor holds under cost pressure).
        """
        if caps.economy_mode and model == ModelName.SONNET and purpose != "critic":
            log.info("economy mode: downgrading %s→Haiku for %s", model.value, purpose)
            return ModelName.HAIKU
        return model

    def text(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: ModelName = ModelName.HAIKU,
        purpose: str = "generate",
        max_tokens: int = 2048,
        caps: CapStatus | None = None,
    ) -> LLMResponse:
        """One plain-text call. Returns the response with token counts."""
        caps = caps or self._ledger.check_caps()
        resolved = self._resolve_model(model, purpose, caps)
        text, in_tok, out_tok, cache_tok = self._client.complete(
            resolved, system, messages, max_tokens
        )
        self._ledger.record(resolved, in_tok, out_tok, purpose, cache_tok)
        return LLMResponse(text, in_tok, out_tok, cache_tok, resolved)

    def structured(
        self,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        model: ModelName = ModelName.HAIKU,
        purpose: str = "generate",
        max_tokens: int = 2048,
        caps: CapStatus | None = None,
    ) -> dict[str, Any]:
        """One structured (JSON) call with reflexive-reprompt on schema violation.

        The schema is a simple dict-shape spec: {"key": type} for top-level keys.
        On a schema-violating response, the model gets one reflexive retry showing
        its bad reply and demanding strict JSON (ported from Task_IQ classifier.py).
        """
        caps = caps or self._ledger.check_caps()
        resolved = self._resolve_model(model, purpose, caps)

        full_messages = list(messages)
        for attempt in range(2):  # one reflexive retry
            text, in_tok, out_tok, cache_tok = self._client.complete(
                resolved, system, full_messages, max_tokens
            )
            self._ledger.record(resolved, in_tok, out_tok, purpose, cache_tok)
            try:
                parsed = json.loads(_strip_fences(text))
                _validate_schema(parsed, schema)
                return parsed
            except (json.JSONDecodeError, SchemaError) as exc:
                if attempt == 0:
                    full_messages.append({"role": "assistant", "content": text})
                    schema_desc = {k: getattr(v, "__name__", str(v)) for k, v in schema.items()}
                    full_messages.append({
                        "role": "user",
                        "content": (
                            "Your reply was not valid. Return ONLY a valid JSON "
                            f"object matching this shape: {json.dumps(schema_desc)} "
                            "with no markdown fences."
                        ),
                    })
                else:
                    raise SchemaError(
                        f"Model returned unusable output twice: {exc}"
                    ) from exc
        raise SchemaError("unreachable")  # pragma: no cover


def _validate_schema(data: Any, schema: dict[str, Any]) -> None:
    """Validate that `data` is a dict with the expected top-level keys and types."""
    if not isinstance(data, dict):
        raise SchemaError(f"expected a JSON object, got {type(data).__name__}")
    for key, expected_type in schema.items():
        if key not in data:
            raise SchemaError(f"missing required key: {key!r}")
        if not isinstance(data[key], expected_type):
            raise SchemaError(
                f"key {key!r} expected {expected_type.__name__}, "
                f"got {type(data[key]).__name__}"
            )
