"""Typed inputs and outputs of the engine (validated with pydantic).

All chip amounts are in chips. Stacks are chips *behind* (not counting chips
already in the pot). ``pot`` is everything in the middle when hero acts,
including bets already made this street.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .cards import CardError, parse_cards, street_from_board, validate_hand_and_board
from .positions import PositionError, positions

Street = Literal["preflop", "flop", "turn", "river"]
VillainType = Literal["unknown", "tight", "loose", "passive", "aggressive"]
ActionKind = Literal["fold", "check", "call", "bet", "raise", "allin"]
STREET_ORDER: tuple[str, ...] = ("preflop", "flop", "turn", "river")


class Seat(BaseModel):
    position: str
    stack: float = Field(ge=0)
    in_hand: bool = True
    villain_type: VillainType = "unknown"


class Action(BaseModel):
    street: Street
    position: str
    action: ActionKind
    amount: float | None = Field(default=None, ge=0)  # bet/raise: total "to" amount this street


class HandInput(BaseModel):
    format: Literal["cash", "sng"]
    small_blind: float = Field(gt=0)
    big_blind: float = Field(gt=0)
    ante: float = Field(default=0, ge=0)
    players: int = Field(ge=2, le=9)
    hero_position: str
    hero_hand: list[str] | str
    board: list[str] | str = []
    pot: float = Field(gt=0)
    to_call: float = Field(default=0, ge=0)
    hero_stack: float = Field(gt=0)
    seats: list[Seat]  # every other seat; in_hand marks villains still in the pot
    actions: list[Action] = []
    payouts: list[float] | None = None  # SnG only, e.g. [50, 30, 20]
    rake_pct: float = Field(default=0, ge=0, le=0.25)  # cash only
    rake_cap: float | None = Field(default=None, ge=0)
    # "bb": pot, to_call, stacks, action amounts and rake cap are in big blinds
    # (blinds and ante are always chips). Converted to chips on validation.
    units: Literal["chips", "bb"] = "chips"

    @model_validator(mode="after")
    def _validate(self) -> "HandInput":
        try:
            hand, board = validate_hand_and_board(self.hero_hand, self.board)
            seats = positions(self.players)
        except (CardError, PositionError) as e:
            raise ValueError(str(e)) from None
        self.hero_hand, self.board = hand, board
        self.hero_position = self.hero_position.upper()
        for s in self.seats:
            s.position = s.position.upper()
        for a in self.actions:
            a.position = a.position.upper()
        if self.hero_position not in seats:
            raise ValueError(f"Hero position {self.hero_position} invalid for {self.players} players")
        names = [s.position for s in self.seats]
        if sorted(names + [self.hero_position]) != sorted(seats):
            raise ValueError(f"Seats must cover every position except hero's: {seats}")
        if not any(s.in_hand for s in self.seats):
            raise ValueError("At least one villain must still be in the hand")
        for a in self.actions:
            if a.position not in seats:
                raise ValueError(f"Action by unknown position {a.position}")
            if STREET_ORDER.index(a.street) > STREET_ORDER.index(self.street):
                raise ValueError(f"Action on {a.street} but the board is on the {self.street}")
            if a.action in ("bet", "raise") and not a.amount:
                raise ValueError(f"{a.action} by {a.position} needs an amount")
        if self.format == "sng":
            if not self.payouts:
                raise ValueError("Sit & Go needs payouts")
            if any(b > a for a, b in zip(self.payouts, self.payouts[1:])):
                raise ValueError("Payouts must be non-increasing")
        if self.units == "bb":
            self._convert_from_bb()
        if self.to_call > self.hero_stack:
            raise ValueError("Amount to call cannot exceed hero's stack")
        return self

    def _convert_from_bb(self) -> None:
        bb = self.big_blind
        self.pot *= bb
        self.to_call *= bb
        self.hero_stack *= bb
        if self.rake_cap is not None:
            self.rake_cap *= bb
        for seat in self.seats:
            seat.stack *= bb
        for a in self.actions:
            if a.amount is not None:
                a.amount *= bb
        self.units = "chips"

    @property
    def street(self) -> str:
        return street_from_board(parse_cards(self.board))

    @property
    def villains(self) -> list[Seat]:
        return [s for s in self.seats if s.in_hand]


class OptionEV(BaseModel):
    id: str  # e.g. "fold", "call", "bet_75", "allin"
    action: Literal["fold", "check", "call", "bet", "raise", "allin"]
    size_chips: float | None = None  # total put in by this action (bet / raise-to increment)
    size_bb: float | None = None
    size_pct_pot: float | None = None
    ev_chips: float  # chip EV relative to folding now
    ev_bb: float
    ev_dollars: float | None = None  # SnG: expected prize equity after the action
    fold_equity: float | None = None
    equity_when_called: float | None = None


class VillainRange(BaseModel):
    position: str
    villain_type: VillainType
    combos: float
    pct_of_hands: float
    grid: list[list[float]]
    source: str  # how the range was built


class EngineResult(BaseModel):
    street: Street
    mode: Literal["preflop_chart", "pushfold", "preflop_ev", "postflop_heuristic"]
    hero_hand: list[str]
    hand_class: str
    hand_description: str
    board_texture: dict | None
    equity: float
    pot_odds: float | None  # X in "X : 1"
    required_equity: float
    spr: float
    effective_stack: float
    effective_stack_bb: float
    in_position: bool
    villains: list[VillainRange]
    options: list[OptionEV]
    best_option: str  # option id the engine recommends
    chart: dict | None = None  # chart lookup details when used
    alternatives: list[dict] = []  # mixed strategy: [{"option": id, "frequency": f}]
    icm: dict | None = None  # SnG: prize equities, bubble factor
    confidence: Literal["high", "medium", "low"]
    notes: list[str] = []
