"""Board texture, hero hand description, draws, and hand-strength ranking."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from . import evaluator
from .cards import RANKS
from .ranges import CLASS_INDEX, Combo, Range, combo, hand_class

_E = {r + s: evaluator.card(r + s) for r in RANKS for s in "shdc"}
_VALUE = {r: 14 - i for i, r in enumerate(RANKS)}  # A=14 ... 2=2


def _values(cards: list[str]) -> list[int]:
    return [_VALUE[c[0]] for c in cards]


def _straight_windows(values: set[int]) -> list[set[int]]:
    vals = set(values) | ({1} if 14 in values else set())
    return [set(range(lo, lo + 5)) & vals for lo in range(1, 11)]


def board_texture(board: list[str]) -> dict | None:
    if not board:
        return None
    suits = Counter(c[1] for c in board)
    ranks = Counter(c[0] for c in board)
    max_suit = max(suits.values())
    values = set(_values(board))
    best_window = max(len(w) for w in _straight_windows(values))
    paired = max(ranks.values()) >= 2
    flop_suits = Counter(c[1] for c in board[:3])
    suitedness = {3: "monotone", 2: "two-tone", 1: "rainbow"}[max(flop_suits.values())]
    wet = 0
    wet += 2 if max_suit >= 3 else (1 if max_suit == 2 and len(board) < 5 else 0)
    wet += 2 if best_window >= 3 else (1 if best_window == 2 else 0)
    wet -= 1 if paired else 0
    texture = "wet" if wet >= 3 else ("semi-wet" if wet >= 2 else "dry")
    return {
        "paired": paired,
        "trips_on_board": max(ranks.values()) >= 3,
        "suitedness": suitedness,
        "flush_possible": max_suit >= 3,
        "flush_draw_possible": max_suit == 2 and len(board) < 5,
        "straight_possible": best_window >= 3,
        "high_card": max(board, key=lambda c: _VALUE[c[0]])[0],
        "texture": texture,
    }


def draws(hole: list[str], board: list[str]) -> dict:
    """Flush and straight draws that use at least one hole card (none on the river)."""
    if len(board) >= 5 or not board:
        return {"flush_draw": False, "oesd": False, "gutshot": False}
    cards = hole + board
    suits = Counter(c[1] for c in cards)
    fd = any(n == 4 and any(h[1] == s for h in hole) for s, n in suits.items())
    allv = set(_values(cards))
    if 14 in allv:
        allv.add(1)
    hole_v = set(_values(hole)) | ({1} if 14 in _values(hole) else set())
    completing = set()
    for lo in range(1, 11):
        window = set(range(lo, lo + 5))
        have = window & allv
        if len(have) == 4 and have & hole_v:
            completing |= window - have
    made_straight = any(len(set(range(lo, lo + 5)) & allv) == 5 for lo in range(1, 11))
    if made_straight:
        return {"flush_draw": fd, "oesd": False, "gutshot": False}
    return {"flush_draw": fd, "oesd": len(completing) >= 2, "gutshot": len(completing) == 1}


def describe_hand(hole: list[str], board: list[str]) -> str:
    """Plain-English made hand plus draws, e.g. ``"top pair, flush draw"``."""
    if not board:
        cls = hand_class(combo(*hole))
        return {2: "pocket pair"}.get(len(cls), "suited" if cls.endswith("s") else "offsuit") + f" ({cls})"
    score = evaluator.evaluate([_E[c] for c in hole + board])
    kind = evaluator.handtype(score)
    hv = sorted(_values(hole), reverse=True)
    bv = sorted(_values(board), reverse=True)
    board_counts = Counter(bv)
    if kind == "Pair":
        if hv[0] == hv[1] and hv[0] not in bv:
            desc = "overpair" if hv[0] > bv[0] else ("underpair" if hv[0] < bv[-1] else "pocket pair below the top card")
        elif max(board_counts.values()) == 2 and not set(hv) & set(bv):
            desc = "board pair only"
        else:
            paired = max(v for v in hv if v in bv)
            uniq = sorted(set(bv), reverse=True)
            desc = ["top pair", "second pair"][uniq.index(paired)] if uniq.index(paired) < 2 else "bottom/weak pair"
    elif kind == "Trips":
        desc = "set" if hv[0] == hv[1] and hv[0] in bv else ("trips on board" if board_counts.most_common(1)[0][1] >= 3 and not set(hv) & set(bv) else "trips")
    elif kind == "High Card":
        desc = ("ace high" if 14 in hv else "high card") + ""
    else:
        desc = kind.lower()
    d = draws(hole, board)
    extras = [n for n, k in (("flush draw", "flush_draw"), ("open-ended straight draw", "oesd"), ("gutshot", "gutshot")) if d[k]]
    return ", ".join([desc] + extras)


@lru_cache(maxsize=1)
def _preflop_strength() -> tuple[float, ...]:
    from .data import preflop_matrix_doc

    doc = preflop_matrix_doc()
    eq, cnt = doc["equity"], doc["count"]
    return tuple(
        sum(e * n for e, n in zip(eq[a], cnt[a])) / sum(cnt[a]) for a in range(len(eq))
    )


def preflop_strength(c: Combo) -> float:
    """All-in equity of the combo's class against a random hand."""
    return _preflop_strength()[CLASS_INDEX[hand_class(c)]]


def range_strengths(r: Range, board: list[str]) -> dict[Combo, float]:
    """Each combo's percentile within ``r`` (0 weakest .. 1 strongest).

    Preflop ranks by equity vs a random hand. Postflop ranks by made hand,
    then lifts draws: combo draws and flush draws to at least 0.65, open-ended
    straight draws to 0.55, gutshots to 0.35 (they continue like medium hands).
    """
    if not r:
        return {}
    if board:
        be = [_E[c] for c in board]
        score = {c: evaluator.evaluate([_E[c[0]], _E[c[1]]] + be) for c in r}
    else:
        score = {c: preflop_strength(c) for c in r}
    order = sorted(r, key=score.get)
    total = sum(r.values())
    pct, cum, i = {}, 0.0, 0
    while i < len(order):  # ties share a percentile
        j = i
        group_w = 0.0
        while j < len(order) and score[order[j]] == score[order[i]]:
            group_w += r[order[j]]
            j += 1
        p = (cum + group_w / 2) / total
        for c in order[i:j]:
            pct[c] = p
        cum += group_w
        i = j
    if board and len(board) < 5:
        for c in r:
            d = draws(list(c), board)
            floor = 0.65 if d["flush_draw"] and (d["oesd"] or d["gutshot"]) else 0.0
            floor = max(floor, 0.65 if d["flush_draw"] else 0.0, 0.55 if d["oesd"] else 0.0, 0.35 if d["gutshot"] else 0.0)
            pct[c] = max(pct[c], floor)
    return pct


def top_fraction(r: Range, strengths: dict[Combo, float], fraction: float) -> Range:
    """The strongest ``fraction`` of the range by weight (boundary combos partially kept)."""
    fraction = min(max(fraction, 0.0), 1.0)
    total = sum(r.values())
    target = fraction * total
    out: Range = {}
    kept = 0.0
    for c in sorted(r, key=lambda c: -strengths[c]):
        if kept >= target - 1e-12:
            break
        w = r[c]
        take = min(w, target - kept)
        out[c] = take
        kept += take
    return out
