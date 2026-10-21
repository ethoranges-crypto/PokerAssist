"""Cash-game preflop chart lookup (100BB, raise-or-fold opens).

Tables of up to 6 players use the 6-max chart, larger tables the 9-max chart.
Positions are mapped by how many players act behind, so other table sizes are
an approximation (flagged on the result).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .cards import parse_cards
from .data import cash_chart
from .positions import position_index, positions
from .ranges import Range, combo, hand_class, parse_range


class ChartError(ValueError):
    pass


@dataclass(frozen=True)
class ChartDecision:
    frequencies: dict[str, float]  # e.g. {"raise": 0.5, "call": 0.0, "fold": 0.5}
    action: str  # most frequent action; ties go to the more aggressive one
    size_bb: float | None  # raise size (total) when raising
    hand_class: str
    chart_id: str
    chart_position: str
    approximate: bool  # table size differs from the chart's


@lru_cache(maxsize=None)
def _range(text: str) -> Range:
    return parse_range(text)


def _chart_for(n_players: int) -> dict:
    return cash_chart("6max" if n_players <= 6 else "9max")


def _map_position(n_players: int, pos: str, seats: list[str]) -> str:
    return seats[len(seats) - n_players + position_index(n_players, pos)]


def _find(entries: list[dict], hero: str, key: str | None = None, villain: str | None = None) -> dict:
    for e in entries:
        if hero in e["hero"] and (key is None or villain in e[key]):
            return e
    raise ChartError(f"No chart entry for {hero}" + (f" vs {villain}" if villain else ""))


def cash_preflop_decision(
    hand,
    n_players: int,
    position: str,
    facing: str = "none",
    opener: str | None = None,
) -> ChartDecision:
    """Chart action for hero.

    ``facing``: ``"none"`` (folded to hero), ``"open"`` (one raise from
    ``opener``, folded to hero) or ``"3bet"`` (hero opened and faces a 3-bet).
    """
    cards = parse_cards(hand)
    if len(cards) != 2 or cards[0] == cards[1]:
        raise ChartError("Hand must be two distinct cards")
    positions(n_players)  # validates the table size
    chart = _chart_for(n_players)
    seats = chart["seats"]
    pos = _map_position(n_players, position.upper(), seats)
    c = combo(*cards)
    sizes = chart["sizes_bb"]
    in_blinds = pos in ("SB", "BB")

    if facing == "none":
        if pos == "BB":
            freqs = {"check": 1.0}
            size = None
        else:
            w = _range(chart["rfi"][pos]).get(c, 0.0)
            freqs = {"raise": w, "fold": 1 - w}
            size = sizes["open_sb"] if pos == "SB" else sizes["open"]
    elif facing == "open":
        if opener is None:
            raise ChartError("facing='open' needs the opener's position")
        if position_index(n_players, opener) >= position_index(n_players, position):
            raise ChartError(f"{position} does not act after {opener}")
        opp = _map_position(n_players, opener.upper(), seats)
        e = _find(chart["vs_open"], pos, "openers", opp)
        r = _range(e["3bet"]).get(c, 0.0)
        k = _range(e["call"]).get(c, 0.0)
        freqs = {"raise": r, "call": k, "fold": max(0.0, 1 - r - k)}
        size = sizes["3bet_oop" if in_blinds else "3bet_ip"]
    elif facing == "3bet":
        if pos == "BB":
            raise ChartError("The BB cannot open, so cannot face a 3-bet")
        e = _find(chart["vs_3bet"], pos)
        r = _range(e["4bet"]).get(c, 0.0)
        k = _range(e["call"]).get(c, 0.0)
        freqs = {"raise": r, "call": k, "fold": max(0.0, 1 - r - k)}
        size = sizes["4bet"]
    else:
        raise ChartError(f"Unknown facing: {facing!r}")

    action = max(freqs, key=freqs.get)
    return ChartDecision(
        frequencies=freqs,
        action=action,
        size_bb=size if action == "raise" else None,
        hand_class=hand_class(c),
        chart_id=chart["id"],
        chart_position=pos,
        approximate=n_players not in (6, 9),
    )
