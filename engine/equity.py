"""Hero equity against one or more villain ranges.

Exact enumeration is used heads-up when the number of (villain combo, runout)
pairs is small (turn/river, narrow flop ranges); otherwise Monte Carlo.
"""

from __future__ import annotations

import random
from bisect import bisect_right
from dataclasses import dataclass
from itertools import accumulate, combinations
from math import comb

from . import evaluator
from .cards import DECK, check_no_duplicates, parse_cards, validate_hand_and_board
from .ranges import Range, combo, parse_range, remove_dead

_EVAL_CARDS = {c: evaluator.card(c) for c in DECK}
DEFAULT_ITERATIONS = 50_000
EXACT_LIMIT = 150_000
_MAX_REJECTIONS = 1_000
_VILLAIN_RETRIES = 50  # redraws per villain before rejecting the whole sample


class EquityError(ValueError):
    pass


@dataclass(frozen=True)
class EquityResult:
    equity: float  # win share, with ties split between the tied players
    win: float  # probability hero wins outright
    tie: float  # probability hero ties for best hand
    samples: int
    exact: bool


def _as_range(r: Range | str) -> Range:
    return parse_range(r) if isinstance(r, str) else r


def equity(
    hero: str | list[str],
    villains: list[Range | str],
    board: str | list[str] = (),
    iterations: int = DEFAULT_ITERATIONS,
    seed: int | None = None,
) -> EquityResult:
    hero, board = validate_hand_and_board(hero, board)
    if not villains:
        raise EquityError("Need at least one villain range")
    dead = hero + board
    ranges = []
    for i, v in enumerate(villains):
        r = remove_dead(_as_range(v), dead)
        if not r:
            raise EquityError(f"Villain {i + 1} range is empty after removing dead cards")
        ranges.append(r)

    need = 5 - len(board)
    if len(ranges) == 1:
        runouts = comb(52 - len(dead) - 2, need)
        if len(ranges[0]) * runouts <= EXACT_LIMIT:
            return _exact_heads_up(hero, board, ranges[0], need)
    if iterations <= 0:
        raise EquityError("iterations must be > 0")
    return _monte_carlo(hero, board, ranges, need, iterations, random.Random(seed))


def _exact_heads_up(hero: list[str], board: list[str], r: Range, need: int) -> EquityResult:
    deck = [c for c in DECK if c not in set(hero + board)]
    hero_e = [_EVAL_CARDS[c] for c in hero]
    board_e = [_EVAL_CARDS[c] for c in board]
    win = tie = total = 0.0
    for (a, b), w in r.items():
        vill_e = [_EVAL_CARDS[a], _EVAL_CARDS[b]]
        rest = [_EVAL_CARDS[c] for c in deck if c != a and c != b]
        for run in combinations(rest, need):
            full = board_e + list(run)
            h = evaluator.evaluate(hero_e + full)
            v = evaluator.evaluate(vill_e + full)
            if h > v:
                win += w
            elif h == v:
                tie += w
            total += w
    if total == 0:
        raise EquityError("No valid villain combos")
    samples = len(r) * comb(len(deck) - 2, need)
    return EquityResult(
        equity=(win + tie / 2) / total, win=win / total, tie=tie / total, samples=samples, exact=True
    )


def _monte_carlo(
    hero: list[str],
    board: list[str],
    ranges: list[Range],
    need: int,
    iterations: int,
    rng: random.Random,
) -> EquityResult:
    combos = [[(_EVAL_CARDS[a], _EVAL_CARDS[b]) for a, b in r] for r in ranges]
    cums = [list(accumulate(r.values())) for r in ranges]
    totals = [c[-1] for c in cums]
    deck = [_EVAL_CARDS[c] for c in DECK if c not in set(hero + board)]
    hero_e = [_EVAL_CARDS[c] for c in hero]
    board_e = [_EVAL_CARDS[c] for c in board]
    extra = min(need + 2 * len(ranges), len(deck))
    evaluate, rand, sample = evaluator.evaluate, rng.random, rng.sample

    win = tie = share = 0.0
    done = rejections = 0
    while done < iterations:
        used: set = set()
        hands = []
        for cs, cum, tot in zip(combos, cums, totals):
            for _ in range(_VILLAIN_RETRIES):
                a, b = cs[bisect_right(cum, rand() * tot)]
                if a not in used and b not in used:
                    break
            else:
                break
            used.add(a)
            used.add(b)
            hands.append((a, b))
        else:
            run = [c for c in sample(deck, extra) if c not in used][:need]
            full = board_e + run
            h = evaluate(hero_e + full)
            scores = [evaluate([a, b] + full) for a, b in hands]
            best = max(scores)
            if h > best:
                win += 1
                share += 1
            elif h == best:
                tie += 1
                share += 1 / (1 + scores.count(h))
            done += 1
            continue
        rejections += 1
        if rejections > _MAX_REJECTIONS and rejections > 10 * done:
            raise EquityError("Villain ranges overlap too heavily to sample")
    return EquityResult(
        equity=share / done, win=win / done, tie=tie / done, samples=done, exact=False
    )


def hand_vs_hand(
    hero: str | list[str], villain: str | list[str], board: str | list[str] = (), **kw
) -> EquityResult:
    """Convenience wrapper: one specific villain hand."""
    v = parse_cards(villain)
    if len(v) != 2:
        raise EquityError("Villain hand must have exactly 2 cards")
    check_no_duplicates(parse_cards(hero) + v + parse_cards(board))
    return equity(hero, [{combo(*v): 1.0}], board, **kw)
