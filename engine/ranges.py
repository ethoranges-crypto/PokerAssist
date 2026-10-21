"""Hand-range parsing and the 13x13 grid.

A range is a ``dict`` mapping a combo (two cards in deck order, e.g.
``("As", "Kd")``) to a weight in (0, 1]. Notation follows the usual
calculator syntax: ``AA``, ``AKs``, ``AKo``, ``AK``, ``22+``, ``ATs+``,
``TT-77``, ``A5s-A2s``, ``AsKs``, ``random``, with optional ``:weight``.
"""

from __future__ import annotations

import re
from itertools import combinations

from .cards import DECK, RANKS, SUITS, CardError, parse_card

Combo = tuple[str, str]
Range = dict[Combo, float]

_ORDER = {c: i for i, c in enumerate(DECK)}
_CLASS_RE = re.compile(r"([AKQJT2-9])([AKQJT2-9])([so]?)")


class RangeError(ValueError):
    pass


def combo(a: str, b: str) -> Combo:
    return (a, b) if _ORDER[a] < _ORDER[b] else (b, a)


ALL_COMBOS: tuple[Combo, ...] = tuple(combo(a, b) for a, b in combinations(DECK, 2))


def _grid_class(i: int, j: int) -> str:
    if i == j:
        return RANKS[i] * 2
    if i < j:
        return RANKS[i] + RANKS[j] + "s"
    return RANKS[j] + RANKS[i] + "o"


# The 169 hand classes in grid order: index = row * 13 + col (see range_to_grid).
CLASSES: tuple[str, ...] = tuple(_grid_class(i, j) for i in range(13) for j in range(13))
CLASS_INDEX = {c: i for i, c in enumerate(CLASSES)}


def hand_class(c: Combo) -> str:
    """``("As", "Kd")`` -> ``"AKo"``; ``("Ah", "Ad")`` -> ``"AA"``."""
    (r1, s1), (r2, s2) = c
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def class_combos(cls: str) -> list[Combo]:
    m = _CLASS_RE.fullmatch(cls)
    if not m:
        raise RangeError(f"Invalid hand class: {cls!r}")
    r1, r2, kind = m.groups()
    if RANKS.index(r1) > RANKS.index(r2):
        r1, r2 = r2, r1
    if r1 == r2:
        if kind:
            raise RangeError(f"Pairs cannot be suited/offsuit: {cls!r}")
        return [combo(r1 + a, r1 + b) for a, b in combinations(SUITS, 2)]
    out = []
    for a in SUITS:
        for b in SUITS:
            suited = a == b
            if (kind == "s" and not suited) or (kind == "o" and suited):
                continue
            out.append(combo(r1 + a, r2 + b))
    return out


def _split_class(token: str) -> tuple[int, int, str]:
    m = _CLASS_RE.fullmatch(token)
    if not m:
        raise RangeError(f"Invalid hand class: {token!r}")
    r1, r2, kind = m.groups()
    i, j = RANKS.index(r1), RANKS.index(r2)
    if i > j:
        i, j = j, i
    if i == j and kind:
        raise RangeError(f"Pairs cannot be suited/offsuit: {token!r}")
    return i, j, kind


def _expand_token(token: str) -> list[str]:
    """Expand ``22+``/``ATs+``/``TT-77``/``A5s-A2s`` into hand classes."""
    if token.endswith("+"):
        i, j, kind = _split_class(token[:-1])
        if i == j:
            return [RANKS[k] * 2 for k in range(0, i + 1)]
        return [RANKS[i] + RANKS[k] + kind for k in range(i + 1, j + 1)]
    if "-" in token:
        lo, hi = token.split("-", 1)
        i1, j1, k1 = _split_class(lo)
        i2, j2, k2 = _split_class(hi)
        if (i1 == j1) != (i2 == j2) or k1 != k2:
            raise RangeError(f"Mismatched span: {token!r}")
        if i1 == j1:
            a, b = sorted((i1, i2))
            return [RANKS[k] * 2 for k in range(a, b + 1)]
        if i1 != i2:
            raise RangeError(f"Span must keep the top card fixed: {token!r}")
        a, b = sorted((j1, j2))
        return [RANKS[i1] + RANKS[k] + k1 for k in range(a, b + 1)]
    _split_class(token)
    return [token]


def _token_combos(token: str) -> list[Combo]:
    if token.lower() in ("random", "any", "100%"):
        return list(ALL_COMBOS)
    if len(token) == 4 and token[1] in SUITS and token[3] in SUITS:
        try:
            a, b = parse_card(token[:2]), parse_card(token[2:])
        except CardError as e:
            raise RangeError(str(e)) from None
        if a == b:
            raise RangeError(f"Combo uses the same card twice: {token!r}")
        return [combo(a, b)]
    return [c for cls in _expand_token(token) for c in class_combos(cls)]


def parse_range(text: str) -> Range:
    out: Range = {}
    for raw in re.split(r"[,\s]+", text.strip()):
        if not raw:
            continue
        token, _, w = raw.partition(":")
        weight = 1.0
        if w:
            try:
                weight = float(w)
            except ValueError:
                raise RangeError(f"Invalid weight in {raw!r}") from None
            if not 0 <= weight <= 1:
                raise RangeError(f"Weight must be in [0, 1]: {raw!r}")
        for c in _token_combos(token):
            if weight > 0:
                out[c] = weight
            else:
                out.pop(c, None)
    return out


def remove_dead(r: Range, dead: list[str]) -> Range:
    dead_set = set(dead)
    return {c: w for c, w in r.items() if c[0] not in dead_set and c[1] not in dead_set}


def combo_count(r: Range) -> float:
    """Weighted number of combos."""
    return sum(r.values())


def range_to_grid(r: Range) -> list[list[float]]:
    """13x13 grid of the weighted fraction of each class present.

    Row/column index follows ``RANKS`` (A first). Pairs sit on the diagonal,
    suited hands above it (row = high card), offsuit hands below it.
    """
    totals = [[0.0] * 13 for _ in range(13)]
    for c, w in r.items():
        (r1, s1), (r2, s2) = c
        i, j = RANKS.index(r1), RANKS.index(r2)
        if s1 == s2 or i == j:
            totals[i][j] += w
        else:
            totals[j][i] += w
    grid = [[0.0] * 13 for _ in range(13)]
    for i in range(13):
        for j in range(13):
            n = 6 if i == j else (4 if i < j else 12)
            grid[i][j] = totals[i][j] / n
    return grid
