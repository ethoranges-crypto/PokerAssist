"""Table positions in preflop action order (first to act ... BB)."""

from __future__ import annotations

POSITIONS: dict[int, tuple[str, ...]] = {
    2: ("SB", "BB"),  # heads-up: the SB is the button
    3: ("BTN", "SB", "BB"),
    4: ("CO", "BTN", "SB", "BB"),
    5: ("HJ", "CO", "BTN", "SB", "BB"),
    6: ("UTG", "HJ", "CO", "BTN", "SB", "BB"),
    7: ("UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"),
    8: ("UTG", "UTG1", "LJ", "HJ", "CO", "BTN", "SB", "BB"),
    9: ("UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB"),
}


class PositionError(ValueError):
    pass


def positions(n_players: int) -> tuple[str, ...]:
    try:
        return POSITIONS[n_players]
    except KeyError:
        raise PositionError(f"Players must be 2-9, got {n_players}") from None


def position_index(n_players: int, pos: str) -> int:
    seats = positions(n_players)
    pos = pos.upper()
    if pos not in seats:
        raise PositionError(f"{pos} is not a position at a {n_players}-handed table: {seats}")
    return seats.index(pos)


def players_behind(n_players: int, pos: str) -> int:
    """Players still to act after ``pos`` preflop."""
    return n_players - 1 - position_index(n_players, pos)


def blind_posted(n_players: int, pos: str) -> float:
    """Blind in BB that ``pos`` has posted before preflop action."""
    idx = position_index(n_players, pos)
    return {n_players - 2: 0.5, n_players - 1: 1.0}.get(idx, 0.0)
