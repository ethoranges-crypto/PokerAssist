"""API-level models: what the LLM may return, and the Recommendation we send back."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.schema import EngineResult, HandInput, OptionEV, VillainRange


class LLMChoice(BaseModel):
    """The only thing the LLM produces: which engine option, and why."""

    option_id: str = Field(description="id of one of the engine's options")
    explanation: str = Field(description="2-4 sentences, using only numbers present in the input")


class Alternative(BaseModel):
    option: str
    action: str
    size_bb: float | None
    frequency: float
    ev_bb: float


class Validation(BaseModel):
    llm_option: str | None = None
    overridden: bool = False  # LLM picked something other than the engine's choice
    numbers_rejected: list[str] = []  # numbers in the LLM text that the engine never produced
    error: str | None = None


class Recommendation(BaseModel):
    action: Literal["fold", "check", "call", "bet", "raise", "allin"]
    option_id: str
    size_chips: float | None
    size_bb: float | None
    size_pct_pot: float | None
    alternatives: list[Alternative]
    ev_bb: float
    ev_dollars: float | None
    equity: float
    pot_odds: float | None
    required_equity: float
    spr: float
    confidence: Literal["high", "medium", "low"]
    explanation: str
    explanation_source: Literal["llm", "engine"]
    hand_description: str
    mode: str
    villains: list[VillainRange]
    options: list[OptionEV]
    icm: dict | None
    chart: dict | None
    notes: list[str]
    validation: Validation
    timing_ms: dict[str, float] = {}
    hand_id: int | None = None  # set when the hand was saved to history


class HandRecord(BaseModel):
    id: int
    created_at: str
    input: HandInput
    recommendation: Recommendation
    notes: str = ""


class HandSummary(BaseModel):
    id: int
    created_at: str
    format: str
    hero_position: str
    hero_hand: list[str]
    board: list[str]
    action: str
    size_bb: float | None
    confidence: str
    notes: str


__all__ = ["EngineResult", "HandInput"]
