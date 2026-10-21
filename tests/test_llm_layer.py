"""The LLM layer may only rank and explain: tested with fake explainers and a fake client."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.llm import SYSTEM_PROMPT, ClaudeExplainer, llm_payload
from app.models import LLMChoice
from app.recommend import recommend
from app.validator import allowed_numbers, unsupported_numbers
from engine.analyze import analyze
from spots import build

SPOTS = json.loads((Path(__file__).parent / "fixtures" / "spots_v1.json").read_text())["spots"]
BY_ID = {s["id"]: s for s in SPOTS}


class Fake:
    def __init__(self, fn):
        self.fn = fn

    def explain(self, inp, result):
        return self.fn(inp, result)


def honest(inp, r):
    best = next(o for o in r.options if o.id == r.best_option)
    return LLMChoice(option_id=r.best_option, explanation=f"{r.hand_description}: {round(r.equity * 100)}% equity, EV {best.ev_bb} BB.")


def test_honest_llm_is_used():
    rec = recommend(build(BY_ID["f32"]), Fake(honest))
    assert rec.explanation_source == "llm"
    assert not rec.validation.overridden and not rec.validation.numbers_rejected


def test_llm_disagreeing_with_engine_is_overridden():
    def contrarian(inp, r):
        other = next(o.id for o in r.options if o.id != r.best_option)
        return LLMChoice(option_id=other, explanation="Do something else.")

    inp = build(BY_ID["f32"])
    rec = recommend(inp, Fake(contrarian))
    assert rec.option_id == analyze(inp).best_option
    assert rec.validation.overridden and rec.explanation_source == "engine"


def test_invented_numbers_replace_the_explanation():
    rec = recommend(build(BY_ID["f32"]), Fake(lambda i, r: LLMChoice(option_id=r.best_option, explanation="You have 91.7% equity.")))
    assert rec.validation.numbers_rejected == ["91.7"]
    assert rec.explanation_source == "engine" and "91.7" not in rec.explanation


def test_llm_failure_falls_back():
    def boom(inp, r):
        raise RuntimeError("network down")

    rec = recommend(build(BY_ID["f32"]), Fake(boom))
    assert rec.explanation_source == "engine" and "network down" in rec.validation.error


def test_no_llm_uses_engine_text():
    rec = recommend(build(BY_ID["p01"]), None)
    assert rec.explanation_source == "engine" and rec.explanation


@pytest.mark.parametrize("spot", SPOTS, ids=[s["id"] for s in SPOTS])
def test_engine_explanations_only_use_engine_numbers(spot):
    """The fallback text obeys the same rule we hold the LLM to."""
    inp = build(spot)
    rec = recommend(inp, None)
    assert unsupported_numbers(rec.explanation, allowed_numbers(inp, analyze(inp))) == []


def test_claude_request_shape():
    captured = {}

    class Messages:
        def parse(self, **kw):
            captured.update(kw)
            return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                                   parsed_output=LLMChoice(option_id="call", explanation="ok"))

    client = SimpleNamespace(beta=SimpleNamespace(messages=Messages()))
    inp = build(BY_ID["f32"])
    out = ClaudeExplainer(client=client).explain(inp, analyze(inp))
    assert out.option_id == "call"
    assert captured["model"] == "claude-sonnet-5-5"
    assert captured["output_format"] is LLMChoice
    assert captured["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in captured["betas"]
    assert "temperature" not in captured  # rejected by this model; determinism comes from the engine
    assert captured["system"][0]["text"] == SYSTEM_PROMPT
    payload = json.loads(captured["messages"][0]["content"])
    assert "grid" not in payload["engine_result"]["villains"][0]


def test_claude_refusal_raises():
    class Messages:
        def parse(self, **kw):
            return SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="general_harms"), parsed_output=None)

    client = SimpleNamespace(beta=SimpleNamespace(messages=Messages()))
    inp = build(BY_ID["f32"])
    rec = recommend(inp, ClaudeExplainer(client=client))
    assert "declined" in rec.validation.error and rec.explanation_source == "engine"


def test_payload_is_compact():
    inp = build(BY_ID["f37"])
    assert len(llm_payload(inp, analyze(inp))) < 12_000
