"""Tests for the call_llm wrapper — routing, reflexive re-prompt, retry, caps."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from coach.call_llm import AnthropicClient, CallLLM, LLMResponse, SchemaError
from coach.config import ModelName
from coach.cost_ledger import CapStatus, CostLedger


class FakeClient:
    """In-memory LLM client for tests — returns scripted responses."""

    def __init__(self, responses: list[tuple[str, int, int, int]]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[ModelName, str, list[dict], int]] = []

    def complete(self, model, system, messages, max_tokens):
        self.calls.append((model, system, messages, max_tokens))
        return self._responses.pop(0)


def _make_ledger() -> CostLedger:
    return CostLedger(daily_budget=1.0, weekly_budget=10.0)


class TestRouting:
    def test_text_routes_to_requested_model(self):
        client = FakeClient([("hello", 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        resp = wrapper.text("sys", [{"role": "user", "content": "hi"}], model=ModelName.SONNET)
        assert resp.model == ModelName.SONNET
        assert resp.text == "hello"
        assert client.calls[0][0] == ModelName.SONNET

    def test_economy_mode_downgrades_sonnet_to_haiku(self):
        client = FakeClient([("ok", 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        caps = CapStatus(economy_mode=True)
        resp = wrapper.text("sys", [{"role": "user", "content": "hi"}],
                            model=ModelName.SONNET, purpose="generate", caps=caps)
        assert resp.model == ModelName.HAIKU
        assert client.calls[0][0] == ModelName.HAIKU

    def test_critic_not_downgraded_in_economy_mode(self):
        client = FakeClient([("ok", 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        caps = CapStatus(economy_mode=True)
        resp = wrapper.text("sys", [{"role": "user", "content": "hi"}],
                            model=ModelName.SONNET, purpose="critic", caps=caps)
        assert resp.model == ModelName.SONNET
        assert client.calls[0][0] == ModelName.SONNET

    def test_haiku_not_downgraded(self):
        client = FakeClient([("ok", 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        caps = CapStatus(economy_mode=True)
        resp = wrapper.text("sys", [{"role": "user", "content": "hi"}],
                            model=ModelName.HAIKU, purpose="generate", caps=caps)
        assert resp.model == ModelName.HAIKU


class TestStructured:
    def test_valid_json_returned(self):
        good = json.dumps({"score": 2, "feedback": "ok"})
        client = FakeClient([(good, 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        result = wrapper.structured(
            "sys", [{"role": "user", "content": "grade this"}],
            schema={"score": int, "feedback": str},
        )
        assert result == {"score": 2, "feedback": "ok"}

    def test_reflexive_retry_on_bad_json(self):
        bad = "not json at all"
        good = json.dumps({"score": 1, "feedback": "weak"})
        client = FakeClient([(bad, 10, 5, 0), (good, 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        result = wrapper.structured(
            "sys", [{"role": "user", "content": "grade this"}],
            schema={"score": int, "feedback": str},
        )
        assert result == {"score": 1, "feedback": "weak"}
        # Second call should include the reflexive re-prompt
        assert len(client.calls) == 2
        second_messages = client.calls[1][2]
        assert any("not valid" in m["content"] for m in second_messages)

    def test_strips_markdown_fences(self):
        fenced = "```json\n" + json.dumps({"score": 3, "feedback": "great"}) + "\n```"
        client = FakeClient([(fenced, 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        result = wrapper.structured(
            "sys", [{"role": "user", "content": "grade this"}],
            schema={"score": int, "feedback": str},
        )
        assert result["score"] == 3

    def test_raises_after_two_failures(self):
        client = FakeClient([("bad1", 10, 5, 0), ("bad2", 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        with pytest.raises(SchemaError, match="unusable output twice"):
            wrapper.structured(
                "sys", [{"role": "user", "content": "grade this"}],
                schema={"score": int, "feedback": str},
            )

    def test_schema_missing_key_raises(self):
        missing = json.dumps({"score": 2})  # no feedback
        client = FakeClient([(missing, 10, 5, 0), (missing, 10, 5, 0)])
        wrapper = CallLLM(client, _make_ledger())
        with pytest.raises(SchemaError):
            wrapper.structured(
                "sys", [{"role": "user", "content": "grade this"}],
                schema={"score": int, "feedback": str},
            )


class TestCostLogging:
    def test_text_call_logged_to_ledger(self):
        client = FakeClient([("hello", 100, 50, 0)])
        ledger = _make_ledger()
        wrapper = CallLLM(client, ledger)
        wrapper.text("sys", [{"role": "user", "content": "hi"}], model=ModelName.HAIKU)
        assert len(ledger.records) == 1
        rec = ledger.records[0]
        assert rec.model == ModelName.HAIKU
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50

    def test_cache_read_tokens_logged(self):
        client = FakeClient([("hello", 100, 50, 200)])
        ledger = _make_ledger()
        wrapper = CallLLM(client, ledger)
        wrapper.text("sys", [{"role": "user", "content": "hi"}], model=ModelName.SONNET)
        assert ledger.records[0].cache_read_tokens == 200
