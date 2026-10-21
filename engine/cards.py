"""Card parsing and input validation.

Cards are two-character strings: rank in ``AKQJT98765432`` then suit in ``shdc``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

RANKS = "AKQJT98765432"
SUITS = "shdc"
DECK = tuple(r + s for r in RANKS for s in SUITS)
STREETS = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}

_CARD_RE = re.compile(r"(10|[2-9TJQKA])([shdc])", re.IGNORECASE)


class CardError(ValueError):
    pass


def parse_card(text: str) -> str:
    m = _CARD_RE.fullmatch(text.strip())
    if not m:
        raise CardError(f"Invalid card: {text!r}")
    rank, suit = m.groups()
    rank = "T" if rank == "10" else rank.upper()
    return rank + suit.lower()


def parse_cards(cards: str | Iterable[str]) -> list[str]:
    """Parse ``"AsKd"``, ``"As Kd"``, ``"As,Kd"`` or ``["As", "Kd"]``."""
    if isinstance(cards, str):
        compact = re.sub(r"[\s,]+", "", cards)
        tokens = _CARD_RE.findall(compact)
        if "".join(r + s for r, s in tokens) != compact:
            raise CardError(f"Invalid cards: {cards!r}")
        return [parse_card(r + s) for r, s in tokens]
    return [parse_card(c) for c in cards]


def street_from_board(board: list[str]) -> str:
    try:
        return STREETS[len(board)]
    except KeyError:
        raise CardError(f"Board must have 0, 3, 4 or 5 cards, got {len(board)}") from None


def check_no_duplicates(cards: list[str]) -> None:
    seen = set()
    for c in cards:
        if c in seen:
            raise CardError(f"Duplicate card: {c}")
        seen.add(c)


def validate_hand_and_board(
    hand: str | Iterable[str], board: str | Iterable[str]
) -> tuple[list[str], list[str]]:
    hand = parse_cards(hand)
    board = parse_cards(board)
    if len(hand) != 2:
        raise CardError(f"Hero hand must have exactly 2 cards, got {len(hand)}")
    street_from_board(board)
    check_no_duplicates(hand + board)
    return hand, board
