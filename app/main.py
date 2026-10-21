"""FastAPI backend. Run: uvicorn app.main:app --reload"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from engine.equity import EquityError, equity
from engine.cards import CardError
from engine.icm import ICMError, bubble_factor, icm
from engine.ranges import RangeError
from engine.schema import HandInput

from .db import HandStore
from .llm import default_explainer
from .models import HandRecord, HandSummary, Recommendation
from .recommend import recommend


class EquityRequest(BaseModel):
    hero: str
    villains: list[str] = Field(min_length=1, description="one range string per villain, e.g. 'QQ+, AK'")
    board: str = ""
    iterations: int = Field(default=50_000, ge=1000, le=500_000)
    seed: int | None = 0


class ICMRequest(BaseModel):
    stacks: list[float]
    payouts: list[float]
    hero: int | None = None
    villain: int | None = None


class NotesRequest(BaseModel):
    notes: str


def create_app(db_path: str | None = None, explainer="default") -> FastAPI:
    app = FastAPI(title="PokerAssist", version="0.3.0")
    store = HandStore(db_path or os.environ.get("POKERASSIST_DB", "pokerassist.sqlite3"))
    llm = default_explainer() if explainer == "default" else explainer

    @app.get("/api/health")
    def health():
        return {"ok": True, "llm": llm is not None}

    @app.post("/api/analyze", response_model=Recommendation)
    def analyze_hand(inp: HandInput, save: bool = True):
        rec = recommend(inp, llm)
        if save:
            rec.hand_id = store.add(inp.model_dump(), rec.model_dump())
        return rec

    @app.post("/api/equity")
    def equity_endpoint(req: EquityRequest):
        try:
            r = equity(req.hero, req.villains, req.board, iterations=req.iterations, seed=req.seed)
        except (CardError, RangeError, EquityError) as e:
            raise HTTPException(422, str(e)) from None
        return r.__dict__

    @app.post("/api/icm")
    def icm_endpoint(req: ICMRequest):
        try:
            out = {"equity": icm(req.stacks, req.payouts)}
            if req.hero is not None and req.villain is not None:
                out["bubble_factor"] = bubble_factor(req.stacks, req.payouts, req.hero, req.villain)
        except (ICMError, IndexError) as e:
            raise HTTPException(422, str(e)) from None
        return out

    @app.get("/api/hands", response_model=list[HandSummary])
    def list_hands(limit: int = 100):
        return [
            HandSummary(
                id=h["id"], created_at=h["created_at"], format=h["input"]["format"],
                hero_position=h["input"]["hero_position"], hero_hand=h["input"]["hero_hand"],
                board=h["input"]["board"], action=h["recommendation"]["action"],
                size_bb=h["recommendation"]["size_bb"], confidence=h["recommendation"]["confidence"],
                notes=h["notes"],
            )
            for h in store.list(limit)
        ]

    @app.get("/api/hands/{hand_id}", response_model=HandRecord)
    def get_hand(hand_id: int):
        h = store.get(hand_id)
        if h is None:
            raise HTTPException(404, "Hand not found")
        return h

    @app.put("/api/hands/{hand_id}/notes")
    def set_notes(hand_id: int, req: NotesRequest):
        if not store.set_notes(hand_id, req.notes):
            raise HTTPException(404, "Hand not found")
        return {"ok": True}

    @app.delete("/api/hands/{hand_id}")
    def delete_hand(hand_id: int):
        if not store.delete(hand_id):
            raise HTTPException(404, "Hand not found")
        return {"ok": True}

    return app


app = create_app()
