"""7-card hand evaluation with an optional C backend.

Uses ``eval7`` (C extension) when it is installed, otherwise a pure-Python
table evaluator, so the engine installs anywhere (eval7 needs a C++ compiler to
build on Windows). Set ``POKERASSIST_EVALUATOR=python`` to force the pure-Python
backend.

Scores are integers, higher is better, and only comparable within one backend.

Pure-Python design: each card is an int carrying a rank prime, a suit nibble and
a rank bit. Without a flush, the product of the rank primes identifies the rank
multiset, looked up in a table built at import (all 5-, 6- and 7-card
multisets). A flush is detected by summing suit nibbles: a nibble reaching 5
sets its high bit after adding 3. The flush suit's rank bitmask is then looked
up in a 13-bit table.
"""

from __future__ import annotations

import os
from itertools import combinations_with_replacement

from .cards import DECK

HAND_TYPES = ("High Card", "Pair", "Two Pair", "Trips", "Straight", "Flush", "Full House", "Quads", "Straight Flush")

_RANK_ORDER = "23456789TJQKA"  # rank value 0..12
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)
_SUIT_INDEX = {"s": 0, "h": 1, "d": 2, "c": 3}
_SHIFT = 20  # category << 20 | five 4-bit rank slots


def _score(category: int, ranks: list[int]) -> int:
    v = category
    for i in range(5):
        v = (v << 4) | (ranks[i] if i < len(ranks) else 0)
    return v


def _straight_high(rank_set: set[int]) -> int | None:
    for hi in range(12, 3, -1):
        if all(r in rank_set for r in range(hi - 4, hi + 1)):
            return hi
    if {12, 0, 1, 2, 3} <= rank_set:  # wheel
        return 3
    return None


def _nonflush_score(counts: list[int]) -> int:
    by_count = sorted(((n, r) for r, n in enumerate(counts) if n), reverse=True)
    ranks_desc = [r for r in range(12, -1, -1) if counts[r]]
    top_n, top_r = by_count[0]
    if top_n == 4:
        return _score(7, [top_r, max(r for r in ranks_desc if r != top_r)])
    trips = [r for n, r in by_count if n >= 3]
    pairs = [r for n, r in by_count if n >= 2]
    if trips and len(pairs) >= 2:
        t = trips[0]
        return _score(6, [t, max(r for r in pairs if r != t)])
    s = _straight_high(set(ranks_desc))
    if s is not None:
        return _score(4, [s])
    if trips:
        t = trips[0]
        return _score(3, [t] + [r for r in ranks_desc if r != t][:2])
    if len(pairs) >= 2:
        p1, p2 = sorted(pairs, reverse=True)[:2]
        return _score(2, [p1, p2, max(r for r in ranks_desc if r not in (p1, p2))])
    if pairs:
        p = pairs[0]
        return _score(1, [p] + [r for r in ranks_desc if r != p][:3])
    return _score(0, ranks_desc[:5])


def _flush_score(mask: int) -> int:
    ranks = [r for r in range(13) if mask >> r & 1]
    s = _straight_high(set(ranks))
    if s is not None:
        return _score(8, [s])
    return _score(5, sorted(ranks, reverse=True)[:5])


def _build_tables() -> tuple[dict[int, int], list[int]]:
    nonflush: dict[int, int] = {}
    for k in (5, 6, 7):
        for combo in combinations_with_replacement(range(13), k):
            counts = [0] * 13
            for r in combo:
                counts[r] += 1
            if max(counts) > 4:
                continue
            key = 1
            for r in combo:
                key *= _PRIMES[r]
            nonflush[key] = _nonflush_score(counts)
    flush = [0] * 8192
    for mask in range(8192):
        if bin(mask).count("1") >= 5:
            flush[mask] = _flush_score(mask)
    return nonflush, flush


# A pure-Python card is its index in DECK; per-card facts live in parallel lists.
_CARD_INDEX = {c: i for i, c in enumerate(DECK)}
_PRIME = [_PRIMES[_RANK_ORDER.index(c[0])] for c in DECK]
_SUIT_ADD = [1 << (4 * _SUIT_INDEX[c[1]]) for c in DECK]
_SUIT = [_SUIT_INDEX[c[1]] for c in DECK]
_RANK_BIT = [1 << _RANK_ORDER.index(c[0]) for c in DECK]
_NONFLUSH: dict[int, int] = {}
_FLUSH: list[int] = []


def _py_card(c: str) -> int:
    return _CARD_INDEX[c]


def _py_evaluate(cards: list[int]) -> int:
    p = 1
    s = 0
    for c in cards:
        p *= _PRIME[c]
        s += _SUIT_ADD[c]
    if (s + 0x3333) & 0x8888:
        for suit in range(4):
            if (s >> (4 * suit)) & 0xF >= 5:
                mask = 0
                for c in cards:
                    if _SUIT[c] == suit:
                        mask |= _RANK_BIT[c]
                return _FLUSH[mask]
    return _NONFLUSH[p]


def _py_handtype(score: int) -> str:
    return HAND_TYPES[score >> _SHIFT]


def _load_backend():
    global _NONFLUSH, _FLUSH
    if os.environ.get("POKERASSIST_EVALUATOR", "").lower() != "python":
        try:
            import eval7

            return "eval7", eval7.Card, eval7.evaluate, eval7.handtype
        except ImportError:
            pass
    _NONFLUSH, _FLUSH = _build_tables()
    return "python", _py_card, _py_evaluate, _py_handtype


BACKEND, card, evaluate, handtype = _load_backend()
"""``card("As")`` -> backend card; ``evaluate([cards])`` -> score; ``handtype(score)`` -> name."""


def evaluate_strs(cards: list[str]) -> int:
    return evaluate([card(c) for c in cards])
