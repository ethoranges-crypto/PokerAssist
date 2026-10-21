import json
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.analyze import analyze
from spots import build

SPOTS = json.loads((Path(__file__).parent / "fixtures" / "spots_v1.json").read_text())["spots"]


def test_fixture_has_fifty_spots():
    assert len(SPOTS) >= 50


@pytest.mark.parametrize("spot", SPOTS, ids=[f"{s['id']}-{s['note']}" for s in SPOTS])
def test_known_spot(spot):
    t = time.perf_counter()
    r = analyze(build(spot))
    elapsed = time.perf_counter() - t
    best = next(o for o in r.options if o.id == r.best_option)
    assert best.action in spot["expect"], f"{spot['note']}: got {best.id} ({[(o.id, o.ev_bb) for o in r.options]})"
    assert elapsed < 2.0  # engine budget inside the 4 s end-to-end target


def test_result_shape_and_key_numbers():
    spot = next(s for s in SPOTS if s["id"] == "f32")
    r = analyze(build(spot))
    assert r.street == "flop" and r.mode == "postflop_heuristic"
    assert r.pot_odds == pytest.approx(825 / 275, rel=1e-3)
    assert r.required_equity == pytest.approx(275 / 1100, abs=1e-3)
    assert r.hand_description == "top pair"
    assert len(r.villains) == 1 and len(r.villains[0].grid) == 13
    assert {o.id for o in r.options} >= {"fold", "call"}
    assert r.confidence == "medium"


def test_preflop_chart_mode_is_high_confidence_with_mixes():
    spot = next(s for s in SPOTS if s["id"] == "p13")
    r = analyze(build(spot))
    assert r.mode == "preflop_chart" and r.confidence == "high"
    assert {a["frequency"] for a in r.alternatives} == {0.5}


def test_sng_reports_icm():
    spot = next(s for s in SPOTS if s["id"] == "s23")
    r = analyze(build(spot))
    assert r.mode == "pushfold"
    assert r.icm["bubble_factor"] > 1
    call = next(o for o in r.options if o.id == "call")
    assert call.ev_chips > 0 and r.best_option == "fold"  # +chip EV but -$EV on the bubble


def test_deterministic():
    spot = next(s for s in SPOTS if s["id"] == "f30")
    assert analyze(build(spot)) == analyze(build(spot))


@pytest.mark.parametrize(
    "patch,msg",
    [
        ({"board": "Kh7c"}, "Board must have"),
        ({"hand": "AhAh"}, "Duplicate"),
        ({"board": "AhKd2c", "hand": "AhKd"}, "Duplicate"),
        ({"to_call": 20000}, "cannot exceed"),
        ({"hero": "UTG2"}, "invalid"),
        ({"format": "sng"}, "payouts"),
        ({"in_hand": []}, "At least one villain"),
    ],
)
def test_input_validation(patch, msg):
    spot = {**next(s for s in SPOTS if s["id"] == "f32"), **patch}
    with pytest.raises(ValidationError, match=msg):
        build(spot)


def test_bb_units_are_converted():
    spot = next(s for s in SPOTS if s["id"] == "f32")
    inp = build(spot)
    inp_bb = inp.model_copy(update={}).model_dump()
    inp_bb.update(units="bb", pot=8.25, to_call=2.75, hero_stack=97.5,
                  seats=[{**s, "stack": s["stack"] / 100} for s in inp_bb["seats"]],
                  actions=[{**a, "amount": None if a["amount"] is None else a["amount"] / 100} for a in inp_bb["actions"]])
    from engine.schema import HandInput
    converted = HandInput(**inp_bb)
    assert converted.pot == pytest.approx(825) and converted.hero_stack == pytest.approx(9750)
