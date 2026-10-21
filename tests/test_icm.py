import json
from itertools import permutations
from pathlib import Path

import pytest

from engine.icm import ICMError, bubble_factor, icm, icm_required_equity

FIXTURES = Path(__file__).parent / "fixtures"


def harville_bruteforce(stacks, payouts):
    """Independent reference: sum over every full finishing order."""
    total = sum(stacks)
    eq = [0.0] * len(stacks)
    for order in permutations(range(len(stacks))):
        p, left = 1.0, total
        for i in order:
            p *= stacks[i] / left
            left -= stacks[i]
        for place, i in enumerate(order[: len(payouts)]):
            eq[i] += p * payouts[place]
    return eq


CASES = json.loads((FIXTURES / "icm_reference.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_matches_reference_within_0_1_percent(case):
    got = icm(case["stacks"], case["payouts"])
    for g, ref in zip(got, case["equity"]):
        assert g == pytest.approx(ref, abs=0.001 * sum(case["payouts"]))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_reference_fixture_agrees_with_bruteforce(case):
    ref = harville_bruteforce(case["stacks"], case["payouts"])
    assert ref == pytest.approx(case["equity"], abs=1e-6)


def test_reference_set_has_ten_cases():
    assert len(CASES) >= 10


def test_basic_properties():
    eq = icm([5000, 3000, 2000], [50, 30, 20])
    assert sum(eq) == pytest.approx(100)
    assert eq[0] > eq[1] > eq[2]
    assert eq[0] < 50 and eq[2] > 20  # ICM flattens equity vs chip share
    assert icm([1, 1, 1], [50, 30, 20]) == pytest.approx([100 / 3] * 3)


def test_heads_up_is_chip_proportional_plus_second():
    a, b = icm([3000, 1000], [70, 30])
    assert a == pytest.approx(30 + 40 * 0.75)
    assert b == pytest.approx(30 + 40 * 0.25)


def test_busted_player_gets_nothing_and_skips_places():
    eq = icm([6000, 4000, 0], [50, 30, 20])
    assert eq[2] == 0  # already out in 3rd: payouts refer to remaining players
    assert sum(eq) == pytest.approx(80)


def test_winner_takes_all_equals_chip_share():
    assert icm([600, 300, 100], [100]) == pytest.approx([60, 30, 10])


def test_validation():
    with pytest.raises(ICMError):
        icm([], [50])
    with pytest.raises(ICMError):
        icm([100, -1], [50])
    with pytest.raises(ICMError):
        icm([100, 100], [])
    with pytest.raises(ICMError):
        icm([100, 100], [30, 50])  # payouts must not increase


def test_bubble_factor_on_bubble():
    # 4 left, 3 paid, equal stacks: losing hurts far more than winning helps.
    bf = bubble_factor([2500] * 4, [50, 30, 20], hero=0, villain=1)
    assert bf > 1.5
    # Winner-take-all is chip EV: bubble factor 1.
    assert bubble_factor([2500] * 4, [100], hero=0, villain=1) == pytest.approx(1.0)


def test_icm_required_equity_exceeds_chip_ev():
    stacks = [2500, 2500, 2500, 2500]
    req = icm_required_equity(stacks, [50, 30, 20], hero=0, villain=1, pot=0, risk=2500)
    assert 0.5 < req < 0.8
    assert icm_required_equity(stacks, [100], hero=0, villain=1, pot=0, risk=2500) == pytest.approx(0.5)
