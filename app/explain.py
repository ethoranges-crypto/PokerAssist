"""Deterministic explanation used when the LLM is unavailable or its text is rejected."""

from __future__ import annotations

from engine.schema import EngineResult, HandInput, OptionEV

_VERB = {"fold": "Fold", "check": "Check", "call": "Call", "bet": "Bet", "raise": "Raise", "allin": "Go all-in"}


def describe_option(o: OptionEV) -> str:
    if o.size_bb is None or o.action in ("fold", "check"):
        return _VERB[o.action]
    pct = f" ({o.size_pct_pot:g}% pot)" if o.action == "bet" and o.size_pct_pot else ""
    return f"{_VERB[o.action]} {o.size_bb:g} BB{pct}"


def engine_explanation(inp: HandInput, r: EngineResult) -> str:
    best = next(o for o in r.options if o.id == r.best_option)
    v = r.villains[0]
    parts = [
        f"{describe_option(best)} with {r.hand_description}: "
        f"{round(100 * r.equity)}% equity against an estimated range of {v.pct_of_hands:g}% of hands."
    ]
    if r.mode == "pushfold" and r.chart:
        parts.append(f"Push/fold chart: {r.chart['action']} (threshold {r.chart['threshold_bb']:g} BB).")
    elif r.mode == "preflop_chart" and r.chart:
        parts.append(f"This follows the {r.chart['chart']} chart for {r.chart['chart_position']}.")
    if inp.to_call > 0:
        parts.append(f"Calling needs {round(100 * r.required_equity)}% equity.")
    others = sorted((o for o in r.options if o.id != best.id), key=lambda o: o.ev_dollars or o.ev_bb, reverse=True)
    if inp.format == "sng" and best.ev_dollars is not None:
        parts.append(f"ICM prize equity: {best.ev_dollars:g} for this option" + (f" vs {others[0].ev_dollars:g} to {describe_option(others[0]).lower()}." if others else "."))
    elif others:
        parts.append(f"Estimated EV {best.ev_bb:g} BB vs {others[0].ev_bb:g} BB to {describe_option(others[0]).lower()}.")
    return " ".join(parts[:4])
