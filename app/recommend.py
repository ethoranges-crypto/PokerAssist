"""HandInput -> Recommendation: engine first, then the (optional) LLM, then validation."""

from __future__ import annotations

import logging
import time

from engine.analyze import analyze
from engine.schema import EngineResult, HandInput

from .explain import engine_explanation
from .llm import Explainer
from .models import Alternative, Recommendation, Validation
from .validator import allowed_numbers, unsupported_numbers

log = logging.getLogger("pokerassist")


def recommend(inp: HandInput, explainer: Explainer | None) -> Recommendation:
    t0 = time.perf_counter()
    result = analyze(inp)
    t1 = time.perf_counter()
    validation = Validation()
    explanation, source = None, "engine"
    if explainer is not None:
        try:
            choice = explainer.explain(inp, result)
            validation.llm_option = choice.option_id
            if choice.option_id != result.best_option:
                validation.overridden = True
                log.warning("LLM chose %s, engine chose %s; using engine", choice.option_id, result.best_option)
            bad = unsupported_numbers(choice.explanation, allowed_numbers(inp, result))
            if bad:
                validation.numbers_rejected = bad
                log.warning("LLM explanation used numbers not in the engine result: %s", bad)
            elif not validation.overridden:
                explanation, source = choice.explanation.strip(), "llm"
        except Exception as e:  # network, refusal, schema: fall back to the engine text
            validation.error = f"{type(e).__name__}: {e}"
            log.warning("LLM explanation failed: %s", validation.error)
    t2 = time.perf_counter()
    if explanation is None:
        explanation = engine_explanation(inp, result)
    return _assemble(inp, result, explanation, source, validation, {"engine": (t1 - t0) * 1000, "llm": (t2 - t1) * 1000})


def _assemble(inp, r: EngineResult, explanation, source, validation, timing) -> Recommendation:
    best = next(o for o in r.options if o.id == r.best_option)
    by_id = {o.id: o for o in r.options}
    alts = [
        Alternative(option=a["option"], action=by_id[a["option"]].action, size_bb=by_id[a["option"]].size_bb,
                    frequency=a["frequency"], ev_bb=by_id[a["option"]].ev_bb)
        for a in r.alternatives
        if a["option"] in by_id
    ]
    return Recommendation(
        action=best.action,
        option_id=best.id,
        size_chips=best.size_chips,
        size_bb=best.size_bb,
        size_pct_pot=best.size_pct_pot,
        alternatives=alts,
        ev_bb=best.ev_bb,
        ev_dollars=best.ev_dollars,
        equity=r.equity,
        pot_odds=r.pot_odds,
        required_equity=r.required_equity,
        spr=r.spr,
        confidence=r.confidence,
        explanation=explanation,
        explanation_source=source,
        hand_description=r.hand_description,
        mode=r.mode,
        villains=r.villains,
        options=r.options,
        icm=r.icm,
        chart=r.chart,
        notes=r.notes,
        validation=validation,
        timing_ms={k: round(v, 1) for k, v in timing.items()},
    )
