"""Claude explanation layer. Ranks and explains engine options; never computes."""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol

import anthropic

from engine.schema import EngineResult, HandInput

from .models import LLMChoice

log = logging.getLogger("pokerassist.llm")

MODEL = os.environ.get("POKERASSIST_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """You explain No-Limit Hold'em decisions computed by a deterministic poker engine.

You receive the hand as entered (hand_input) and the engine's analysis (engine_result) as JSON. The engine has already done all the math: equity, pot odds, villain ranges, fold equity, EV of every option, and ICM for Sit & Go.

Your job:
1. option_id: choose the engine option to recommend. engine_result.best_option is the engine's choice (the highest-EV option; preflop, the chart action). Pick it.
2. explanation: 2-4 plain-English sentences on why, for a player at the table. Ground every claim in the engine output: the hand description, equity vs the villain range, pot odds or required equity, fold equity, the EV comparison with the next best option, ICM or chart notes, and the confidence when it is low.

Numbers: use only numbers that appear in the input, copied as given (a fraction such as equity 0.58 may be written as 58%). Do not add, subtract, convert or estimate anything. If a number is not in the input, describe it in words instead."""


class Explainer(Protocol):
    def explain(self, inp: HandInput, result: EngineResult) -> LLMChoice: ...


def llm_payload(inp: HandInput, result: EngineResult) -> str:
    r = result.model_dump()
    for v in r["villains"]:
        v.pop("grid", None)  # 169 numbers the explanation should not quote
    return json.dumps({"hand_input": inp.model_dump(), "engine_result": r}, separators=(",", ":"))


class ClaudeExplainer:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic(max_retries=1, timeout=8.0)
        self.model = model

    def explain(self, inp: HandInput, result: EngineResult) -> LLMChoice:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=1024,
            # Thinking off: the task is short and latency-bound (spec: < 4 s end to end).
            thinking={"type": "between_tools"},
            output_config={"effort": "low"},
            # Refusal fallback: server-side, routed by refusal category.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": llm_payload(inp, result)}],
            output_format=LLMChoice,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"LLM declined ({getattr(response.stop_details, 'category', None)})")
        if response.parsed_output is None:
            raise RuntimeError(f"LLM returned no parsable output (stop_reason={response.stop_reason})")
        return response.parsed_output


def default_explainer() -> Explainer | None:
    """Claude when credentials are configured, otherwise None (engine explanations)."""
    if os.environ.get("POKERASSIST_DISABLE_LLM"):
        return None
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    return ClaudeExplainer()
