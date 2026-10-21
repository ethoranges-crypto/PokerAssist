"""HandInput -> EngineResult. Deterministic; no LLM calls.

Flow: estimate each villain's range, compute hero equity, then
  * preflop, Sit & Go at <= 15 BB effective: push/fold mode, ranked by ICM $EV
    (the chip-EV Nash chart is reported alongside);
  * preflop spots the cash charts cover: chart action, EV per option as a cross-check;
  * everything else: EV per candidate action, best EV wins.
"""

from __future__ import annotations

import math
from functools import lru_cache

from . import ev as E
from .board import board_texture, describe_hand, range_strengths, top_fraction
from .data import load_json, preflop_matrix_doc
from .equity import equity
from .odds import pot_odds_ratio, required_equity
from .positions import blind_posted
from .preflop import ChartError, cash_preflop_decision, cash_range
from .pushfold import PushFoldError, pushfold_decision, pushfold_range
from .ranges import (
    CLASS_INDEX,
    Range,
    combo,
    combo_count,
    hand_class,
    parse_range,
    range_to_grid,
    remove_dead,
)
from .schema import EngineResult, HandInput, OptionEV, VillainRange
from .villain import action_order_after, effective_bb, estimate_range, hero_in_position, start_stack

PUSHFOLD_BB = 15.0
BET_SIZES = (33, 50, 75, 100, 150)  # % of pot
POSTFLOP_RAISE_MULTS = (2.5, 3.5)  # raise to N x villain's bet
REALIZE = {"preflop": (0.9, 0.75), "postflop": (1.0, 0.9)}  # (in position, out of position)
# Exponent on the minimum defence frequency: >1 folds more, <1 calls more.
# Unknown villains slightly over-defend, so pure bluffs are a little -EV at any size.
DEFENCE_EXP = {"unknown": 0.95, "tight": 1.3, "loose": 0.6, "passive": 0.75, "aggressive": 0.95}
RAISED_DEFENCE = 0.6  # villain already bet this street: continues more vs a raise
LIMPER_DEFENCE = 0.5  # limpers rarely fold to a raise
# Postflop all-in is a candidate only at low SPR: at most this many pots.
POSTFLOP_SHOVE_POTS = 2.5
DEEP_SHOVE_BB = 25  # preflop all-in is a candidate only this short, or facing a 3-bet+
# Future-street value of a hand ahead of villain: (2*eq - 1) * this * pot per street left.
IMPLIED_PER_STREET = 0.25
STREETS_LEFT = {"preflop": 3, "flop": 2, "turn": 1, "river": 0}
EQUITY_ITERS = 20_000
CALLED_ITERS = 6_000
# EVs within max(TIE_BB, TIE_POT x pot) count as equal; the less risky option wins.
TIE_BB = 0.1
TIE_POT = 0.01


# --- equity helpers ---------------------------------------------------------


@lru_cache(maxsize=1)
def _matrix() -> tuple:
    doc = preflop_matrix_doc()
    return tuple(tuple(r) for r in doc["equity"])


def _preflop_equity_hu(hero: list[str], r: Range) -> float:
    m = _matrix()
    h = CLASS_INDEX[hand_class(combo(*hero))]
    r = remove_dead(r, hero)
    total = sum(r.values())
    return sum(w * m[h][CLASS_INDEX[hand_class(c)]] for c, w in r.items()) / total


def _equity(hero: list[str], ranges: list[Range], board: list[str], iters: int) -> float:
    ranges = [r for r in ranges if r]
    if not ranges:
        return 1.0
    if not board and len(ranges) == 1:
        return _preflop_equity_hu(hero, ranges[0])
    return equity(hero, ranges, board, iterations=iters, seed=0).equity


def _union(*rs: Range) -> Range:
    out: Range = {}
    for r in rs:
        for c, w in r.items():
            out[c] = min(1.0, out.get(c, 0.0) + w)
    return out


def _weight(r: Range) -> float:
    return sum(r.values())


# --- street bookkeeping -----------------------------------------------------


def _in_street(inp: HandInput, pos: str) -> float:
    """Chips ``pos`` has already put in on the current street."""
    amt = 0.0
    if inp.street == "preflop":
        amt = blind_posted(inp.players, pos) * inp.big_blind
    for a in inp.actions:
        if a.street == inp.street and a.position == pos and a.amount is not None:
            amt = max(amt, a.amount)
    return amt


def _preflop_context(inp: HandInput) -> dict:
    level, raisers, limpers, allin_raise = 0, [], [], False
    for a in (a for a in inp.actions if a.street == "preflop"):
        if a.position == inp.hero_position:
            continue
        if a.action in ("raise", "bet", "allin"):
            level += 1
            raisers.append(a.position)
            seat = next(s for s in inp.seats if s.position == a.position)
            allin_raise = a.action == "allin" or seat.stack == 0
        elif a.action == "call" and level == 0 and a.position != "BB":
            limpers.append(a.position)
    hero_raised = any(
        a.position == inp.hero_position and a.street == "preflop" and a.action in ("raise", "bet", "allin")
        for a in inp.actions
    )
    level += int(hero_raised)
    if hero_raised:
        raisers.insert(0, inp.hero_position)
    return {"level": level, "raisers": raisers, "limpers": limpers, "allin_raise": allin_raise, "hero_raised": hero_raised}


# --- main -------------------------------------------------------------------


def analyze(inp: HandInput) -> EngineResult:
    bb = inp.big_blind
    hero, board, street = inp.hero_hand, inp.board, inp.street
    villains = inp.villains
    est = {v.position: estimate_range(inp, v) for v in villains}
    ranges = {p: r for p, (r, _) in est.items()}
    hero_in0 = _in_street(inp, inp.hero_position)
    eff = min(inp.hero_stack, max(v.stack + _in_street(inp, v.position) - hero_in0 for v in villains))
    eff = max(eff, min(inp.to_call, inp.hero_stack))
    eff_bb = eff / bb
    start_eff_bb = effective_bb(inp, villains) if street == "preflop" else eff_bb
    ip = hero_in_position(inp)
    phase = "preflop" if street == "preflop" else "postflop"
    realize = 1.0 if street == "river" else REALIZE[phase][0 if ip else 1]
    rake = E.Rake(inp.rake_pct, inp.rake_cap) if inp.format == "cash" and street != "preflop" else E.NO_RAKE
    eq_now = _equity(hero, list(ranges.values()), board, EQUITY_ITERS)
    notes: list[str] = []

    ctx = _preflop_context(inp) if street == "preflop" else None
    mode = "postflop_heuristic"
    chart_info = None
    allowed = None  # restrict option kinds (push/fold)
    if ctx is not None:
        mode = "preflop_ev"
        if inp.format == "sng" and start_eff_bb <= PUSHFOLD_BB:
            chart_info = _pushfold_chart(inp, ctx, start_eff_bb)
            if chart_info:
                mode = "pushfold"
                allowed = {"fold", "allin"} if ctx["level"] == 0 else {"fold", "call"}
                notes.append(f"Push/fold mode: {start_eff_bb:.1f} BB effective (<= {PUSHFOLD_BB:g}).")
        else:
            chart_info = _cash_chart(inp, ctx)
            if chart_info:
                mode = "preflop_chart"
    table = _icm_table(inp) if inp.format == "sng" else None

    hero_in = _in_street(inp, inp.hero_position)
    order = action_order_after(inp, inp.hero_position)
    main_villain = _main_villain(inp, order)

    icm_calls = None
    if mode == "pushfold" and table is not None and ctx["level"] == 0:
        icm_calls = _icm_equilibrium_calls(inp, table, order, hero_in)
        notes.append("Villain calling ranges solved for ICM (push/fold equilibrium for this table).")

    def responses(add: float) -> list[E.Response]:
        out = []
        for pos in order:
            seat = next(s for s in villains if s.position == pos)
            v_in = _in_street(inp, pos)
            hero_risk = max(0.0, min(add, v_in + seat.stack - hero_in))
            v_adds = max(0.0, hero_in + hero_risk - v_in)
            if icm_calls is not None and add >= inp.hero_stack - 1e-9:
                cont = {c: w * icm_calls[pos].get(c, 0.0) for c, w in ranges[pos].items() if icm_calls[pos].get(c)}
            else:
                cont = _continue_range(inp, ctx, pos, ranges[pos], add, seat.villain_type, mode)
            base = _weight(ranges[pos])
            fold_p = 1 - min(1.0, _weight(cont) / base) if base else 1.0
            eq_c = _equity(hero, [cont], board, CALLED_ITERS) if cont else 1.0
            all_in = hero_risk >= inp.hero_stack - 1e-9 or v_adds >= seat.stack - 1e-9
            behind = 0.0 if all_in else min(inp.hero_stack - hero_risk, seat.stack - v_adds)
            implied = _implied(inp, eq_c, inp.pot + hero_risk + v_adds, behind)
            out.append(E.Response(pos, fold_p, eq_c, hero_risk, v_adds, 1.0 if all_in else realize, implied))
        return out

    opts: list[OptionEV] = []

    def add_option(oid, action, size, ev_chips, ev_dollars=None, fe=None, eq_c=None):
        opts.append(
            OptionEV(
                id=oid,
                action=action,
                size_chips=None if size is None else round(size, 2),
                size_bb=None if size is None else round(size / bb, 2),
                size_pct_pot=None if size is None else round(100 * size / inp.pot),
                ev_chips=round(ev_chips, 2),
                ev_bb=round(ev_chips / bb, 3),
                ev_dollars=None if ev_dollars is None else round(ev_dollars, 4),
                fold_equity=None if fe is None else round(fe, 3),
                equity_when_called=None if eq_c is None else round(eq_c, 3),
            )
        )

    def aggressive(oid, action, add):
        rs = responses(add)
        evc, fe = E.aggressive_ev(inp.pot, rs, rake)
        evd = E.aggressive_dollars(table, inp.pot, rs) if table else None
        called = [r for r in rs if r.fold_prob < 1]
        eq_c = sum(r.equity * (1 - r.fold_prob) for r in called) / sum(1 - r.fold_prob for r in called) if called else None
        add_option(oid, action, add, evc, evd, fe, eq_c)

    # fold / check / call
    if inp.to_call > 0:
        add_option("fold", "fold", None, 0.0, E.fold_dollars(table, inp.pot) if table else None)
        call_amt = min(inp.to_call, inp.hero_stack)
        pot_eff = inp.pot - (inp.to_call - call_amt)
        all_in_call = call_amt >= inp.hero_stack - 1e-9 or _facing_allin(inp)
        r_call = 1.0 if all_in_call else realize
        evd = E.call_dollars(table, pot_eff, call_amt, eq_now, r_call) if table else None
        behind = 0.0 if all_in_call else min(inp.hero_stack - call_amt, min(v.stack for v in villains))
        implied = _implied(inp, eq_now, pot_eff + call_amt, behind)
        add_option("call", "call", call_amt,
                   E.call_ev(pot_eff, call_amt, eq_now, r_call, rake, implied), evd, None, eq_now)
        if call_amt >= inp.hero_stack - 1e-9:
            notes.append("Calling puts hero all-in.")
    else:
        implied = _implied(inp, eq_now, inp.pot, min(inp.hero_stack, min(v.stack for v in villains)))
        add_option("check", "check", None, E.check_ev(inp.pot, eq_now, realize, rake, implied),
                   E.check_dollars(table, inp.pot, eq_now, realize) if table else None)

    # bets / raises
    can_raise = not _facing_allin(inp) and inp.hero_stack > inp.to_call
    if can_raise:
        for oid, action, add in _aggressive_sizes(inp, ctx, hero_in, ip, mode, chart_info):
            if allowed is None or action == "allin":
                aggressive(oid, action, add)

    if allowed is not None:
        opts = [o for o in opts if o.action in allowed or o.id in allowed]

    # best option
    key = (lambda o: o.ev_dollars) if table else (lambda o: o.ev_chips)
    tie = max(TIE_BB * bb, TIE_POT * inp.pot) if not table else 1e-4 * sum(inp.payouts)
    risk_rank = {"fold": 0, "check": 1, "call": 2, "bet": 3, "raise": 3, "allin": 4}
    best_ev = max(opts, key=key)
    near = [o for o in opts if key(best_ev) - key(o) <= tie]
    ev_best = min(near, key=lambda o: (risk_rank[o.action], o.size_chips or 0))
    best = ev_best
    alternatives: list[dict] = []
    if mode == "preflop_chart":
        best = _option_for_chart(opts, chart_info["action"])
        alternatives = _chart_alternatives(opts, chart_info["frequencies"])
        if best.id != ev_best.id:
            notes.append(
                f"Chart says {best.id}; the simplified EV model prefers {ev_best.id}. Preflop the chart is trusted."
            )
    elif mode == "pushfold":
        chart_act = chart_info["action"]
        if table and best.action not in (chart_act, "allin" if chart_act == "push" else chart_act):
            notes.append(f"Chip-EV Nash chart says {chart_act}; ICM changes the decision.")
    else:
        alternatives = _ev_alternatives(opts, best, key, inp.pot if not table else None)

    # key numbers & ICM
    icm_info = None
    if table:
        icm_info = _icm_info(inp, table, opts, main_villain)
    villain_out = [
        VillainRange(
            position=p,
            villain_type=next(s.villain_type for s in villains if s.position == p),
            combos=round(combo_count(r), 1),
            pct_of_hands=round(100 * combo_count(r) / 1326, 1),
            grid=[[round(x, 2) for x in row] for row in range_to_grid(r)],
            source=est[p][1],
        )
        for p, r in ranges.items()
    ]
    confidence = _confidence(mode, inp, est, chart_info)
    if len(villains) > 1 and street != "preflop":
        notes.append("Multiway pot: fold equity treats villains independently and ignores overcalls.")
    if mode == "postflop_heuristic":
        notes.append("Postflop EV uses heuristic villain ranges and fold-equity estimates (no solver).")

    return EngineResult(
        street=street,
        mode=mode,
        hero_hand=hero,
        hand_class=hand_class(combo(*hero)),
        hand_description=describe_hand(hero, board),
        board_texture=board_texture(board),
        equity=round(eq_now, 3),
        pot_odds=None if inp.to_call == 0 else round(pot_odds_ratio(inp.pot, inp.to_call), 2),
        required_equity=round(required_equity(inp.pot, min(inp.to_call, inp.hero_stack)), 3),
        spr=round(eff / inp.pot, 2),
        effective_stack=round(eff, 2),
        effective_stack_bb=round(eff_bb, 1),
        in_position=ip,
        villains=villain_out,
        options=opts,
        best_option=best.id,
        chart=chart_info,
        alternatives=alternatives,
        icm=icm_info,
        confidence=confidence,
        notes=notes,
    )


# --- pieces -----------------------------------------------------------------


def _facing_allin(inp: HandInput) -> bool:
    for a in inp.actions:
        if a.street == inp.street and a.position != inp.hero_position and a.action == "allin":
            return True
    return False


def _main_villain(inp: HandInput, order: list[str]) -> str:
    for a in reversed(inp.actions):
        if a.position != inp.hero_position and a.action in ("bet", "raise", "allin") and a.position in order:
            return a.position
    return order[0]


def _pushfold_chart(inp: HandInput, ctx: dict, eff_bb: float) -> dict | None:
    ante_bb = inp.ante / inp.big_blind
    try:
        if ctx["level"] == 0 and not ctx["limpers"] and inp.hero_position != "BB":
            d = pushfold_decision(inp.hero_hand, inp.players, inp.hero_position, eff_bb, ante_bb)
        elif ctx["level"] == 1 and ctx["allin_raise"] and not ctx["hero_raised"]:
            d = pushfold_decision(inp.hero_hand, inp.players, inp.hero_position, eff_bb, ante_bb, pusher=ctx["raisers"][0])
        else:
            return None
    except PushFoldError:
        return None
    return {"type": "pushfold", "action": d.action, "threshold_bb": d.threshold_bb, "chart": d.chart, "hand_class": d.hand_class}


def _cash_chart(inp: HandInput, ctx: dict) -> dict | None:
    if ctx["limpers"]:
        return None
    try:
        if ctx["level"] == 0:
            d = cash_preflop_decision(inp.hero_hand, inp.players, inp.hero_position, "none")
        elif ctx["level"] == 1 and not ctx["hero_raised"]:
            d = cash_preflop_decision(inp.hero_hand, inp.players, inp.hero_position, "open", ctx["raisers"][0])
        elif ctx["level"] == 2 and ctx["hero_raised"] and len(ctx["raisers"]) == 2:
            d = cash_preflop_decision(inp.hero_hand, inp.players, inp.hero_position, "3bet")
        else:
            return None
    except ChartError:
        return None
    return {
        "type": "cash",
        "chart": d.chart_id,
        "chart_position": d.chart_position,
        "action": d.action,
        "frequencies": {k: round(v, 3) for k, v in d.frequencies.items()},
        "approximate": d.approximate,
        "hand_class": d.hand_class,
    }


def _aggressive_sizes(inp, ctx, hero_in, ip, mode, chart_info) -> list[tuple[str, str, float]]:
    """(option id, action, chips hero adds) for bets/raises, capped at the stack."""
    bb = inp.big_blind
    stack = inp.hero_stack
    out = []

    def push(oid, action, add):
        add = round(add, 2)
        if add >= stack * 0.9:
            return
        if add > inp.to_call and all(abs(add - a) > 1e-6 for _, _, a in out):
            out.append((oid, action, add))

    if inp.street == "preflop":
        v_to = inp.to_call + hero_in  # amount hero faces in total
        if ctx["level"] == 0:
            to = (3.0 if inp.hero_position == "SB" else 2.5) * bb + bb * len(ctx["limpers"])
            if inp.hero_position == "BB":
                to = (4.0 + len(ctx["limpers"])) * bb
            push("raise", "raise", to - hero_in)
        elif ctx["level"] == 1:
            mult = 3.0 if ip and inp.hero_position not in ("SB", "BB") else 4.0
            push("raise", "raise", mult * v_to - hero_in)
        else:
            push("raise", "raise", 2.2 * v_to - hero_in)
    elif inp.to_call == 0:
        for pct in BET_SIZES:
            push(f"bet_{pct}", "bet", inp.pot * pct / 100)
    else:
        v_to = inp.to_call + hero_in
        for m in POSTFLOP_RAISE_MULTS:
            push(f"raise_{m:g}x", "raise", m * v_to - hero_in)
    if inp.street == "preflop":
        shove_ok = ctx["level"] >= 2 or stack / bb <= DEEP_SHOVE_BB
    else:
        shove_ok = stack <= POSTFLOP_SHOVE_POTS * (inp.pot + inp.to_call)
    if shove_ok or inp.to_call >= stack * 0.9:
        out.append(("allin", "allin", stack))
    return out


def _continue_range(inp, ctx, pos, r: Range, add: float, vtype: str, mode: str) -> Range:
    """Part of villain ``pos``'s range that continues vs hero adding ``add`` chips."""
    if not r:
        return {}
    dead = inp.hero_hand + inp.board
    if inp.street == "preflop":
        n = inp.players
        chart_r = None
        try:
            seat = next(v for v in inp.seats if v.position == pos)
            if mode == "pushfold" or (inp.format == "sng" and add >= inp.hero_stack - 1e-9 and effective_bb(inp, [seat]) <= 20):
                stack_bb = effective_bb(inp, [next(v for v in inp.seats if v.position == pos)])
                chart_r = pushfold_range(n, pos, stack_bb, inp.ante / inp.big_blind, pusher=inp.hero_position)
            elif add >= inp.hero_stack - 1e-9:
                g = load_json("ranges/generic_v1.json")
                chart_r = parse_range(g["call_shove_deep"])
            elif ctx["level"] == 0:
                chart_r = _union(cash_range(n, "3bet", pos, inp.hero_position), cash_range(n, "call_open", pos, inp.hero_position))
            elif ctx["level"] == 1 and pos == ctx["raisers"][0]:
                chart_r = _union(cash_range(n, "4bet", pos), cash_range(n, "call_3bet", pos))
            else:
                g = load_json("ranges/generic_v1.json")
                chart_r = _union(parse_range(g["four_bet"]), parse_range(g["call_four_bet"]))
        except (ChartError, PushFoldError, KeyError):
            chart_r = None
        if chart_r is not None:
            out = {c: w * chart_r[c] for c, w in r.items() if c in chart_r}
            return remove_dead(out, dead)
        exp = DEFENCE_EXP[vtype] * (LIMPER_DEFENCE if pos in ctx["limpers"] else 1.0)
        frac = (inp.pot / (inp.pot + add)) ** exp
        return top_fraction(r, range_strengths(r, []), frac)
    frac = (inp.pot / (inp.pot + add)) ** _defence_exponent(vtype, add / inp.pot, _in_street(inp, pos) > 0)
    return top_fraction(r, range_strengths(r, inp.board), frac)


def _defence_exponent(vtype: str, size_to_pot: float, invested: bool) -> float:
    """Exponent on the minimum defence frequency for a villain facing a bet.

    Type and "already bet" adjustments apply in full up to a pot-sized bet and
    fade out by 3x pot, where villains defend at the plain (unknown) rate:
    nobody calls off a huge shove light, and nobody folds everything to one.
    """
    w = 1.0 if size_to_pot <= 1 else max(0.0, 1 - (size_to_pot - 1) / 2)
    base = DEFENCE_EXP["unknown"]
    exp = base + (DEFENCE_EXP[vtype] - base) * w
    if invested:
        exp *= 1 + (RAISED_DEFENCE - 1) * w
    return exp


def _implied(inp: HandInput, eq: float, pot_after: float, behind: float) -> float:
    """Chips a hand ahead of villain expects to win on later streets (0 when all-in)."""
    if behind <= 0:
        return 0.0
    gain = max(0.0, 2 * eq - 1) * IMPLIED_PER_STREET * pot_after * STREETS_LEFT[inp.street]
    return min(gain, 0.5 * behind)


def _villain_icm_required(t: E.Table, pos: str, pot: float, hero_risk: float, v_adds: float) -> float | None:
    """Equity villain ``pos`` needs to call hero's shove under ICM."""
    names = list(t.stacks)
    def val(deltas):
        s = [max(0.0, t.stacks[n] + deltas.get(n, 0.0)) for n in names]
        from .icm import icm
        return icm(s, t.payouts)[names.index(pos)]
    fold = val({t.hero: pot})
    win = val({pos: pot + hero_risk})
    lose = val({pos: -v_adds, t.hero: pot + v_adds})
    if win <= lose:
        return None
    return (fold - lose) / (win - lose)


def _icm_equilibrium_calls(inp: HandInput, t: E.Table, order: list[str], hero_in: float) -> dict[str, Range]:
    """Each villain's ICM-equilibrium calling range vs hero's open shove."""
    from .pushfold import ICMCaller, PreflopMatrix, solve_icm_pushfold
    from .ranges import CLASSES, class_combos

    callers = []
    for pos in order:
        seat = next(s for s in inp.seats if s.position == pos)
        v_in = _in_street(inp, pos)
        risk = max(0.0, min(inp.hero_stack, v_in + seat.stack - hero_in))
        v_adds = max(0.0, hero_in + risk - v_in)
        req = _villain_icm_required(t, pos, inp.pot, risk, v_adds)
        win = t.value({t.hero: inp.pot + v_adds, pos: -v_adds})
        lose = t.value({t.hero: -risk, pos: inp.pot + risk})
        callers.append(ICMCaller(pos, 1.0 if req is None else req, win, lose))
    m = PreflopMatrix.from_json(preflop_matrix_doc())
    _, calls = solve_icm_pushfold(m, callers, t.value({t.pot_taker: inp.pot}), t.value({t.hero: inp.pot}))
    out = {}
    for pos, freq in calls.items():
        out[pos] = {c: float(freq[i]) for i, cls in enumerate(CLASSES) if freq[i] > 0.01 for c in class_combos(cls)}
    return out


def _stack(inp: HandInput, pos: str) -> float:
    return next(s.stack for s in inp.seats if s.position == pos)


def _icm_table(inp: HandInput) -> E.Table:
    stacks = {inp.hero_position: inp.hero_stack}
    stacks.update({s.position: s.stack for s in inp.seats})
    order = action_order_after(inp, inp.hero_position)
    return E.Table(stacks=stacks, payouts=list(inp.payouts), hero=inp.hero_position, pot_taker=_main_villain(inp, order))


def _icm_info(inp: HandInput, table: E.Table, opts: list[OptionEV], villain: str) -> dict:
    from .icm import ICMError, bubble_factor

    names = list(table.stacks)
    stacks = [start_stack(inp, n) for n in names]  # stacks before this hand's betting
    try:
        bf = bubble_factor(stacks, table.payouts, names.index(table.hero), names.index(villain))
    except ICMError:
        bf = None
    info = {
        "prize_pool": sum(table.payouts),
        "hero_equity_if_fold": round(E.fold_dollars(table, inp.pot), 4),
        "bubble_factor_vs": villain,
        "bubble_factor": None if bf is None else round(bf, 2),
    }
    if inp.to_call > 0:
        eq_needed = _icm_required_call_equity(inp, table)
        if eq_needed is not None:
            info["icm_required_equity"] = round(eq_needed, 3)
    return info


def _icm_required_call_equity(inp: HandInput, t: E.Table) -> float | None:
    call = min(inp.to_call, inp.hero_stack)
    pot = inp.pot - (inp.to_call - call)
    fold = t.value({t.pot_taker: pot})
    win = t.value({t.hero: pot})
    lose = t.value({t.hero: -call, t.pot_taker: pot + call})
    if math.isclose(win, lose):
        return None
    return (fold - lose) / (win - lose)


def _option_for_chart(opts: list[OptionEV], action: str) -> OptionEV:
    want = {"raise": ("raise", "allin"), "call": ("call",), "fold": ("fold",), "check": ("check",)}[action]
    for kind in want:
        for o in opts:
            if o.action == kind or o.id == kind:
                return o
    return opts[0]


def _chart_alternatives(opts: list[OptionEV], freqs: dict[str, float]) -> list[dict]:
    live = {k: v for k, v in freqs.items() if v > 0}
    if len(live) < 2:
        return []
    return [{"option": _option_for_chart(opts, k).id, "frequency": round(v, 2)} for k, v in sorted(live.items(), key=lambda kv: -kv[1])]


def _ev_alternatives(opts, best, key, pot) -> list[dict]:
    """Mixed strategy when other options are nearly as good: softmax over EV."""
    temp = 0.015 * pot if pot else 0.002 * max(abs(key(o)) for o in opts) + 1e-9
    weights = {o.id: math.exp((key(o) - key(best)) / temp) for o in opts if o.id == best.id or o.action != "fold"}
    total = sum(weights.values())
    freqs = {k: w / total for k, w in weights.items() if w / total >= 0.15}
    if len(freqs) < 2:
        return []
    s = sum(freqs.values())
    return [{"option": k, "frequency": round(v / s, 2)} for k, v in sorted(freqs.items(), key=lambda kv: -kv[1])]


def _confidence(mode: str, inp: HandInput, est: dict, chart_info: dict | None) -> str:
    thin = any("default range" in src for _, src in est.values())
    if mode == "pushfold":
        return "high"
    if mode == "preflop_chart":
        return "medium" if (chart_info or {}).get("approximate") or thin else "high"
    if len(inp.villains) > 1 or thin or mode == "preflop_ev":
        return "low"
    return "medium"

