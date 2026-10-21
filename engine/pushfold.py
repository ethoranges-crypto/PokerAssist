"""Push/fold Nash equilibrium (chip EV) for short-stacked preflop play.

Model: folded to the pusher, who shoves or folds; each player behind then calls
or folds in turn, and the first call ends the action (no overcalls). Everyone
has the same effective stack. Card removal is exact between pusher and caller,
and ignored for players who folded. Solved by fictitious play over the 169 hand
classes using the precomputed preflop equity matrix.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .cards import parse_cards
from .data import pushfold_chart
from .positions import blind_posted, position_index, positions
from .ranges import CLASS_INDEX, CLASSES, combo, hand_class

TOTAL_COMBOS = 1225  # combos of two cards from the 50 unseen
# Prior probability of being dealt each class (grid order): combos / 1326.
CLASS_PRIOR = (
    np.array([6 if r == c else (4 if r < c else 12) for r in range(13) for c in range(13)]) / 1326
)


@dataclass(frozen=True)
class PreflopMatrix:
    equity: np.ndarray  # equity[a, b]: class a vs class b
    count: np.ndarray  # count[a, b]: combos of b compatible with one combo of a

    @property
    def weighted(self) -> np.ndarray:
        return self.equity * self.count

    @classmethod
    def from_json(cls, doc: dict) -> "PreflopMatrix":
        return cls(np.array(doc["equity"], dtype=float), np.array(doc["count"], dtype=float))


@dataclass(frozen=True)
class PushFoldSolution:
    push: np.ndarray  # push frequency per class (169,)
    calls: dict[str, np.ndarray]  # caller position -> call frequency per class
    exploitability_bb: float  # largest gain any player gets by deviating


def _setup(n_players: int, pusher: str, stack_bb: float, ante_bb: float):
    seats = positions(n_players)
    i = seats.index(pusher)
    callers = list(seats[i + 1 :])
    if not callers:
        raise ValueError("The BB cannot open-shove; nobody is behind")
    post = {p: blind_posted(n_players, p) + ante_bb for p in seats}
    if stack_bb <= max(post.values()):
        raise ValueError("Stack must exceed the largest blind + ante")
    dead = 1.5 + n_players * ante_bb
    pots = {
        j: n_players * ante_bb
        + 2 * (stack_bb - ante_bb)
        + sum(blind_posted(n_players, p) for p in seats if p not in (pusher, j))
        for j in callers
    }
    fold_value = {p: stack_bb - post[p] for p in seats}
    steal_value = stack_bb - post[pusher] + dead
    return callers, pots, fold_value, steal_value


def _push_evs(m, wn, callers, call_freqs, pots, steal_value):
    """Final stack (BB) of pushing each class, given callers' strategies."""
    ev = np.zeros(169)
    p_reach = np.ones(169)
    for j in callers:
        f = call_freqs[j]
        p_call = m.count @ f / TOTAL_COMBOS
        ev += p_reach * (wn @ f) / TOTAL_COMBOS * pots[j]
        p_reach = p_reach * (1 - p_call)
    return ev + p_reach * steal_value


def _call_evs(m, wn, push, pot):
    """Final stack of calling with each class against the push range."""
    combos = m.count @ push
    with np.errstate(invalid="ignore", divide="ignore"):
        eq = np.where(combos > 0, (wn @ push) / combos, 0.0)
    return eq * pot


def _best_response(ev: np.ndarray, fold: float) -> np.ndarray:
    return np.where(ev > fold, 1.0, np.where(ev == fold, 0.5, 0.0))


def solve_pushfold(
    m: PreflopMatrix,
    n_players: int,
    pusher: str,
    stack_bb: float,
    ante_bb: float = 0.0,
    iterations: int = 1500,
) -> PushFoldSolution:
    callers, pots, fold_value, steal_value = _setup(n_players, pusher, stack_bb, ante_bb)
    wn = m.weighted
    push = np.ones(169)
    calls = {j: np.full(169, 0.5) for j in callers}
    for t in range(1, iterations + 1):
        step = 1 / (t + 1)
        br_push = _best_response(
            _push_evs(m, wn, callers, calls, pots, steal_value), fold_value[pusher]
        )
        for j in callers:
            br = _best_response(_call_evs(m, wn, push, pots[j]), fold_value[j])
            calls[j] += (br - calls[j]) * step
        push += (br_push - push) * step

    prior = CLASS_PRIOR
    # Exploitability: average gain (BB) from switching to a best response.
    gains = []
    ev = _push_evs(m, wn, callers, calls, pots, steal_value)
    cur = push * ev + (1 - push) * fold_value[pusher]
    gains.append(prior @ (np.maximum(ev, fold_value[pusher]) - cur))
    for j in callers:
        ev_c = _call_evs(m, wn, push, pots[j])
        cur_c = calls[j] * ev_c + (1 - calls[j]) * fold_value[j]
        # Caller only faces the decision when reached; weight by reach of a push.
        gains.append(prior @ (np.maximum(ev_c, fold_value[j]) - cur_c) * (prior @ push))
    return PushFoldSolution(push=push, calls=calls, exploitability_bb=float(max(gains)))


# --- Chart lookup -----------------------------------------------------------


class PushFoldError(ValueError):
    pass


@dataclass(frozen=True)
class PushFoldDecision:
    action: str  # "push", "call" or "fold"
    hand_class: str
    threshold_bb: float  # act at or below this effective stack; 0 = never
    stack_bb: float
    ante_bb: float  # ante of the chart used (nearest available)
    chart: str


def pushfold_decision(
    hand,
    n_players: int,
    position: str,
    stack_bb: float,
    ante_bb: float = 0.0,
    pusher: str | None = None,
    chart: dict | None = None,
) -> PushFoldDecision:
    """Shove/fold when folded to hero, or call/fold when ``pusher`` has shoved.

    ``stack_bb`` is the effective stack in big blinds.
    """
    chart = chart or pushfold_chart()
    cards = parse_cards(hand)
    if len(cards) != 2 or cards[0] == cards[1]:
        raise PushFoldError("Hand must be two distinct cards")
    if stack_bb <= 0:
        raise PushFoldError("Stack must be > 0")
    if stack_bb > chart["max_stack"]:
        raise PushFoldError(f"Push/fold charts cover stacks up to {chart['max_stack']} BB")
    position = position.upper()
    hero_idx = position_index(n_players, position)
    ante = min(chart["antes"], key=lambda a: abs(a - ante_bb))
    table = chart["charts"][str(ante)][str(n_players)]

    if pusher is None:
        if position not in table["push"]:
            raise PushFoldError(f"{position} cannot open-shove (nobody behind)")
        grid = table["push"][position]
        yes, label = "push", f"push {position}"
    else:
        pusher = pusher.upper()
        if position_index(n_players, pusher) >= hero_idx:
            raise PushFoldError(f"{position} does not act after {pusher}")
        grid = table["call"][pusher][position]
        yes, label = "call", f"call {position} vs {pusher}"

    cls = hand_class(combo(*cards))
    row, col = divmod(CLASS_INDEX[cls], 13)
    threshold = grid[row][col]
    # Below the smallest charted stack, use the smallest stack's ranges.
    lookup_stack = max(stack_bb, chart["stack_grid"][0])
    return PushFoldDecision(
        action=yes if threshold > 0 and lookup_stack <= threshold else "fold",
        hand_class=cls,
        threshold_bb=threshold,
        stack_bb=stack_bb,
        ante_bb=ante,
        chart=f"nash_v{chart['version']} {n_players}-handed ante={ante} {label}",
    )


def pushfold_range(
    n_players: int,
    position: str,
    stack_bb: float,
    ante_bb: float = 0.0,
    pusher: str | None = None,
    chart: dict | None = None,
) -> dict:
    """Nash shove range for ``position`` (or its calling range vs ``pusher``) as a Range."""
    from .ranges import class_combos

    chart = chart or pushfold_chart()
    ante = min(chart["antes"], key=lambda a: abs(a - ante_bb))
    table = chart["charts"][str(ante)][str(n_players)]
    position = position.upper()
    grid = table["push"][position] if pusher is None else table["call"][pusher.upper()][position]
    stack = min(max(stack_bb, chart["stack_grid"][0]), chart["max_stack"])
    out = {}
    for i, cls in enumerate(CLASSES):
        if grid[i // 13][i % 13] >= stack:
            for c in class_combos(cls):
                out[c] = 1.0
    return out


# --- ICM push/fold equilibrium for one spot ----------------------------------


@dataclass(frozen=True)
class ICMCaller:
    position: str
    required_equity: float  # equity this villain needs to call under ICM
    win: float  # hero's prize equity if hero beats this caller
    lose: float  # hero's prize equity if this caller wins


def solve_icm_pushfold(
    m: PreflopMatrix,
    callers: list[ICMCaller],
    fold_value: float,
    steal_value: float,
    iterations: int = 400,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Hero shoves into ``callers`` (in order); payoffs are prize equities.

    Each caller calls a class iff its equity vs hero's shove range meets their
    ICM required equity; hero shoves a class iff its $EV beats folding.
    Fictitious play; returns (push frequency, {caller: call frequency}).
    """
    wn = m.weighted
    push = np.ones(169)
    calls = {c.position: np.full(169, 0.5) for c in callers}
    for t in range(1, iterations + 1):
        step = 1 / (t + 1)
        ev = np.zeros(169)
        reach = np.ones(169)
        for c in callers:
            f = calls[c.position]
            combos = m.count @ f
            p_call = combos / TOTAL_COMBOS
            with np.errstate(invalid="ignore", divide="ignore"):
                eq = np.where(combos > 0, (wn @ f) / combos, 0.0)
            ev += reach * p_call * (eq * c.win + (1 - eq) * c.lose)
            reach = reach * (1 - p_call)
        ev += reach * steal_value
        br_push = _best_response(ev, fold_value)
        vs = m.count @ push
        with np.errstate(invalid="ignore", divide="ignore"):
            eq_vs_push = np.where(vs > 0, (wn @ push) / vs, 0.0)
        for c in callers:
            br = _best_response(eq_vs_push, c.required_equity)
            calls[c.position] += (br - calls[c.position]) * step
        push += (br_push - push) * step
    return push, calls
