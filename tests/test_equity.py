import json
import time
from pathlib import Path

import pytest

from engine.cards import CardError
from engine.equity import EquityError, equity, hand_vs_hand

FIXTURES = Path(__file__).parent / "fixtures"
TOLERANCE = 0.01  # spec: within ±1% of a reference calculator


def test_aa_vs_kk_preflop():
    r = hand_vs_hand("AsAh", "KdKc", seed=1)
    assert r.equity == pytest.approx(0.82, abs=TOLERANCE)
    assert not r.exact


@pytest.mark.parametrize(
    "hero,expected",
    # PokerStove/Equilab published equities vs a random hand.
    [("AsAh", 0.852), ("KsKh", 0.824), ("AsKs", 0.670), ("7s2h", 0.346), ("2s2h", 0.503)],
)
def test_preflop_vs_random(hero, expected):
    assert equity(hero, ["random"], seed=7).equity == pytest.approx(expected, abs=TOLERANCE)


def _reference_spots():
    spots = json.loads((FIXTURES / "equity_reference.json").read_text())["spots"]
    return [pytest.param(s, id=f"{s['hero']}-vs-{'|'.join(s['villains'])}-{s['board'] or 'pre'}") for s in spots]


@pytest.mark.parametrize("spot", _reference_spots())
def test_matches_reference_calculator(spot):
    r = equity(spot["hero"], spot["villains"], spot["board"], seed=42)
    assert r.equity == pytest.approx(spot["equity"], abs=TOLERANCE)


def test_reference_set_has_twenty_spots():
    assert len(_reference_spots()) >= 20


def test_river_is_exact_and_deterministic():
    r = equity("KsQs", ["AA"], "Js2d3h4c8d")
    assert r.exact
    assert r.equity == 0.0
    assert r.samples == 6


def test_river_chop():
    r = hand_vs_hand("2c3d", "4h5s", "AsKsQsJsTs")
    assert r.exact and r.tie == 1.0 and r.equity == 0.5


def test_turn_uses_exact_enumeration():
    r = equity("AsKd", ["random"], "Ts9s2c7h")
    assert r.exact


def test_seed_makes_monte_carlo_reproducible():
    a = equity("AsKd", ["random"], "Ts9s2c", seed=3)
    b = equity("AsKd", ["random"], "Ts9s2c", seed=3)
    assert a == b


def test_win_tie_equity_consistent():
    r = equity("AsKd", ["AK"], "", seed=5)
    assert r.win + r.tie <= 1.0
    assert r.win <= r.equity <= r.win + r.tie
    assert r.tie > 0.8  # AK vs AK chops most of the time


def test_weighted_range():
    # Against 100% AA + a token weight of 72o, KK is near its equity vs AA.
    near_aa = equity("KsKh", ["AA, 72o:0.01"], seed=9).equity
    assert near_aa == pytest.approx(0.18, abs=0.02)


def test_multiway_equity_lower_than_heads_up():
    hu = equity("AsAh", ["random"], seed=1).equity
    three = equity("AsAh", ["random", "random"], seed=1).equity
    assert three < hu
    assert three == pytest.approx(0.735, abs=TOLERANCE)


def test_dead_cards_removed_from_range():
    # The only villain combo uses a card hero holds.
    with pytest.raises(EquityError, match="empty"):
        equity("AsKd", ["AsAh"])


def test_invalid_inputs():
    with pytest.raises(CardError):
        equity("AsAs", ["random"])
    with pytest.raises(CardError):
        equity("AsKd", ["random"], "2c3c")
    with pytest.raises(EquityError):
        equity("AsKd", [])
    with pytest.raises(CardError):
        hand_vs_hand("AsKd", "AsQd")


@pytest.mark.parametrize(
    "hero,villains,board",
    [
        ("AsKd", ["random"], ""),
        ("AsKd", ["random"], "Ts9s2c"),
        ("AsAh", ["random", "random", "random"], ""),
        ("QhQd", ["JJ+,AQs+,AKo,T9s"], "Th9c4d"),
    ],
)
def test_under_one_second(hero, villains, board):
    t = time.perf_counter()
    equity(hero, villains, board, seed=1)
    assert time.perf_counter() - t < 1.0
