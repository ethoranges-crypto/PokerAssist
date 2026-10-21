"""Pot odds, SPR and simple chip-EV helpers.

Convention: ``pot`` is everything in the middle when hero is to act, including
any bets villains have already made on this street. ``to_call`` is the extra
amount hero must put in to call.
"""

from __future__ import annotations


class OddsError(ValueError):
    pass


def _check_non_negative(**values: float) -> None:
    for name, v in values.items():
        if v < 0:
            raise OddsError(f"{name} must be >= 0, got {v}")


def required_equity(pot: float, to_call: float) -> float:
    """Equity hero needs for a call to break even: call / (pot + call)."""
    _check_non_negative(pot=pot, to_call=to_call)
    if to_call == 0:
        return 0.0
    return to_call / (pot + to_call)


def pot_odds_ratio(pot: float, to_call: float) -> float | None:
    """Pot odds as ``X`` in "X : 1". ``None`` when there is nothing to call."""
    _check_non_negative(pot=pot, to_call=to_call)
    if to_call == 0:
        return None
    return pot / to_call


def spr(effective: float, pot: float) -> float:
    """Stack-to-pot ratio."""
    _check_non_negative(effective=effective, pot=pot)
    if pot == 0:
        raise OddsError("SPR undefined for an empty pot")
    return effective / pot


def effective_stack(hero: float, villains: list[float]) -> float:
    """Hero's stack capped by the largest villain stack still in the hand."""
    if not villains:
        raise OddsError("Need at least one villain stack")
    _check_non_negative(hero=hero, **{f"villain_{i}": v for i, v in enumerate(villains)})
    return min(hero, max(villains))


def call_ev(equity: float, pot: float, to_call: float) -> float:
    """Chip EV of calling relative to folding, assuming no further betting."""
    _check_non_negative(pot=pot, to_call=to_call)
    if not 0 <= equity <= 1:
        raise OddsError(f"equity must be in [0, 1], got {equity}")
    return equity * (pot + to_call) - to_call


def to_bb(chips: float, big_blind: float) -> float:
    if big_blind <= 0:
        raise OddsError("big_blind must be > 0")
    return chips / big_blind
