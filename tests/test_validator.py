import json
from pathlib import Path

import pytest

from app.validator import allowed_numbers, numbers_in, unsupported_numbers
from engine.analyze import analyze
from spots import build

SPOTS = {s["id"]: s for s in json.loads((Path(__file__).parent / "fixtures" / "spots_v1.json").read_text())["spots"]}


@pytest.fixture(scope="module")
def ctx():
    inp = build(SPOTS["f32"])
    r = analyze(inp)
    return inp, r, allowed_numbers(inp, r)


def test_extracts_numbers_but_not_card_or_bet_words():
    text = "With AhKd on Kh7c2d, a 3-bet pot at a 6-max table: 84% equity, raise to 9.62 BB, 1,300 chips, $25.5."
    assert [v for _, v in numbers_in(text)] == [84, 9.62, 1300, 25.5]


def test_engine_numbers_pass(ctx):
    inp, r, allowed = ctx
    best = next(o for o in r.options if o.id == r.best_option)
    text = (
        f"Top pair with {round(100 * r.equity)}% equity. You need {round(100 * r.required_equity)}% to call; "
        f"raising to {best.size_bb} BB has EV {best.ev_bb} BB. Pot odds {r.pot_odds} to 1, pot {inp.pot:g}."
    )
    assert unsupported_numbers(text, allowed) == []


def test_invented_numbers_are_caught(ctx):
    _, _, allowed = ctx
    assert unsupported_numbers("You are 73.4% to win and should bet 17.3 BB.", allowed) == ["73.4", "17.3"]


def test_grid_values_do_not_whitelist_numbers(ctx):
    inp, r, _ = ctx
    from app.validator import _walk

    assert all(isinstance(x, float) for x in _walk({"grid": [[0.37]]}, skip={"grid"})) is True
    assert 0.37 not in set(_walk({"grid": [[0.37]]}, skip={"grid"}))
