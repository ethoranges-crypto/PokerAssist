"""Villain range estimation: positional defaults narrowed by each action.

Preflop ranges come from the cash charts (or push/fold charts when stacks are
short), multiplied together action by action, then widened or tightened by
villain type. Postflop, each bet/call/check reweights combos by their strength
percentile on that street's board. All thresholds are heuristics.
"""

from __future__ import annotations

from .board import preflop_strength, range_strengths
from .data import load_json
from .positions import blind_posted, positions
from .preflop import ChartError, cash_range
from .pushfold import PushFoldError, pushfold_range
from .ranges import ALL_COMBOS, Range, parse_range, remove_dead
from .schema import STREET_ORDER, Action, HandInput, Seat

PUSHFOLD_MAX_BB = 20.0

# Postflop reweighting by villain type.
BET_VALUE_THRESHOLD = {"unknown": 0.55, "tight": 0.62, "loose": 0.5, "passive": 0.7, "aggressive": 0.45}
BLUFF_WEIGHT = {"unknown": 0.15, "tight": 0.08, "loose": 0.25, "passive": 0.05, "aggressive": 0.3}
CALL_FLOOR = {"unknown": 0.3, "tight": 0.4, "loose": 0.15, "passive": 0.2, "aggressive": 0.35}
WEAK_CALL_WEIGHT = {"unknown": 0.15, "tight": 0.05, "loose": 0.35, "passive": 0.25, "aggressive": 0.1}
CHECK_TRAP_WEIGHT = {"unknown": 0.4, "tight": 0.4, "loose": 0.4, "passive": 0.7, "aggressive": 0.25}


def _generic() -> dict:
    return load_json("ranges/generic_v1.json")


def _random() -> Range:
    return dict.fromkeys(ALL_COMBOS, 1.0)


def _intersect(a: Range, b: Range) -> Range:
    return {c: w * b[c] for c, w in a.items() if c in b and w * b[c] > 0}


def start_stack(inp: HandInput, pos: str) -> float:
    """Stack at the start of the hand: chips behind plus everything put in this hand."""
    behind = inp.hero_stack if pos == inp.hero_position else next(s.stack for s in inp.seats if s.position == pos)
    put_in = 0.0
    for street in STREET_ORDER:
        amt = blind_posted(inp.players, pos) * inp.big_blind if street == "preflop" else 0.0
        for a in inp.actions:
            if a.street == street and a.position == pos and a.amount is not None:
                amt = max(amt, a.amount)
            elif a.street == street and a.position == pos and a.action == "call":
                amt = max(amt, _street_bet(inp, street, a))
        put_in += amt
    return behind + put_in


def _street_bet(inp: HandInput, street: str, call: Action) -> float:
    """Largest bet on ``street`` before ``call`` (what the caller matched)."""
    best = inp.big_blind if street == "preflop" else 0.0
    for a in inp.actions:
        if a is call:
            break
        if a.street == street and a.amount is not None:
            best = max(best, a.amount)
    return best


def effective_bb(inp: HandInput, seats: list[Seat]) -> float:
    """Start-of-hand effective stack (BB) between hero and the biggest of ``seats``."""
    hero = start_stack(inp, inp.hero_position)
    return min(hero, max(start_stack(inp, s.position) for s in seats)) / inp.big_blind


def _resize(r: Range, factor: float) -> Range:
    """Tighten (factor < 1) or widen (factor > 1) by preflop strength."""
    if factor == 1 or not r:
        return r
    total = sum(r.values())
    if factor < 1:
        keep, out = total * factor, {}
        for c in sorted(r, key=preflop_strength, reverse=True):
            if keep <= 0:
                break
            out[c] = min(r[c], keep)
            keep -= out[c]
        return out
    add = total * (factor - 1)
    out = dict(r)
    for c in sorted((c for c in ALL_COMBOS if r.get(c, 0) < 1), key=preflop_strength, reverse=True):
        if add <= 0:
            break
        extra = min(1 - out.get(c, 0), add)
        out[c] = out.get(c, 0) + extra
        add -= extra
    return out


def _preflop_action_range(inp: HandInput, a: Action, level: int, raisers: list[str], stack_bb: float) -> tuple[Range, str]:
    n, g = inp.players, _generic()
    pos = a.position
    short = inp.format == "sng" and stack_bb <= PUSHFOLD_MAX_BB
    ante_bb = inp.ante / inp.big_blind
    try:
        if a.action in ("raise", "bet", "allin"):
            if level == 0:
                if short and pos != "BB":
                    return pushfold_range(n, pos, stack_bb, ante_bb), "push/fold shove range"
                return cash_range(n, "rfi", pos), "open-raise chart"
            if level == 1:
                if short:
                    return pushfold_range(n, pos, stack_bb, ante_bb, pusher=raisers[0]), "push/fold re-shove (call) range"
                return cash_range(n, "3bet", pos, raisers[0]), f"3-bet chart vs {raisers[0]}"
            if level == 2:
                return parse_range(g["four_bet"]), "generic 4-bet range"
            return parse_range(g["five_bet_allin"]), "generic 5-bet range"
        if a.action == "call":
            if level == 0:
                return parse_range(g["limp"]), "generic limp range"
            if level == 1:
                if short:
                    return pushfold_range(n, pos, stack_bb, ante_bb, pusher=raisers[0]), "push/fold call range"
                return cash_range(n, "call_open", pos, raisers[0]), f"flat-call chart vs {raisers[0]}"
            if level == 2 and pos == raisers[0]:
                return cash_range(n, "call_3bet", pos), "call-3-bet chart"
            return parse_range(g["call_four_bet"]), "generic call vs 3-bet+ range"
        if a.action == "check":
            r = _random()
            strong = set(_resize(r, 0.1))
            return {c: (0.3 if c in strong else 1.0) for c in r}, "checked option (premiums mostly raise)"
    except (ChartError, PushFoldError, KeyError):
        pass
    return parse_range(g["unknown_preflop"]), "generic preflop range (spot not charted)"


def preflop_range(inp: HandInput, seat: Seat) -> tuple[Range, list[str]]:
    stack_bb = effective_bb(inp, [seat])
    r = _random()
    sources: list[str] = []
    level, raisers = 0, []
    for a in (a for a in inp.actions if a.street == "preflop"):
        if a.position == seat.position and a.action != "fold":
            rng, src = _preflop_action_range(inp, a, level, raisers, stack_bb)
            r = _intersect(r, rng) or r
            sources.append(src)
        if a.action in ("raise", "bet", "allin"):
            level += 1
            raisers.append(a.position)
    if not sources:
        if inp.street == "preflop":
            sources.append("yet to act (any two cards)")
        else:
            r = parse_range(_generic()["unknown_preflop"])
            sources.append("default range (no preflop action entered)")
    factor = _generic()["type_widths"][seat.villain_type]
    if factor != 1:
        r = _resize(r, factor)
        sources.append(f"{seat.villain_type} adjustment x{factor}")
    return r, sources


def _street_board(board: list[str], street: str) -> list[str]:
    return board[: {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]]


def narrow_postflop(r: Range, inp: HandInput, seat: Seat) -> tuple[Range, list[str]]:
    t = seat.villain_type
    sources = []
    for street in STREET_ORDER[1 : STREET_ORDER.index(inp.street) + 1]:
        board = _street_board(inp.board, street)
        for a in (a for a in inp.actions if a.street == street and a.position == seat.position):
            r = remove_dead(r, inp.hero_hand + board)
            s = range_strengths(r, board)
            if a.action in ("bet", "raise", "allin"):
                raise_bump = 0.12 if a.action != "bet" else 0.0
                q = min(0.9, BET_VALUE_THRESHOLD[t] + raise_bump)
                bluff = BLUFF_WEIGHT[t] * (0.5 if raise_bump else 1)
                r = {c: w * (1.0 if s[c] >= q else bluff) for c, w in r.items()}
            elif a.action == "call":
                r = {
                    c: w * (0.6 if s[c] >= 0.9 else 1.0 if s[c] >= CALL_FLOOR[t] else WEAK_CALL_WEIGHT[t])
                    for c, w in r.items()
                }
            elif a.action == "check":
                r = {c: w * (CHECK_TRAP_WEIGHT[t] if s[c] >= 0.85 else 1.0) for c, w in r.items()}
            sources.append(f"{street} {a.action}")
    return {c: w for c, w in r.items() if w > 1e-6}, sources


def estimate_range(inp: HandInput, seat: Seat) -> tuple[Range, str]:
    r, src = preflop_range(inp, seat)
    r = remove_dead(r, inp.hero_hand + inp.board)
    if inp.street != "preflop":
        r2, post = narrow_postflop(r, inp, seat)
        r = r2 or r
        src += post
    if not r:
        r = remove_dead(_random(), inp.hero_hand + inp.board)
        src.append("fell back to any two cards")
    return r, "; ".join(src)


def action_order_after(inp: HandInput, hero: str) -> list[str]:
    """Villains in hand in the order they act after hero on this street."""
    seats = list(positions(inp.players))
    if inp.street != "preflop":
        # Postflop the blinds act first and the button last.
        seats = seats[-2:] + seats[:-2] if inp.players > 2 else ["BB", "SB"]
    i = seats.index(hero)
    order = seats[i + 1 :] + seats[:i]
    in_hand = {s.position for s in inp.villains}
    return [p for p in order if p in in_hand]


def hero_in_position(inp: HandInput) -> bool:
    seats = list(positions(inp.players))
    post = seats[-2:] + seats[:-2] if inp.players > 2 else ["BB", "SB"]
    alive = [p for p in post if p == inp.hero_position or p in {s.position for s in inp.villains}]
    return alive[-1] == inp.hero_position
