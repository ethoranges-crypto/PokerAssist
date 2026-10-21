import numpy as np
import pytest

from engine.data import preflop_matrix_doc, pushfold_chart
from engine.positions import POSITIONS
from engine.pushfold import (
    CLASS_PRIOR,
    PreflopMatrix,
    PushFoldError,
    pushfold_decision,
    solve_pushfold,
)
from engine.ranges import CLASS_INDEX, CLASSES


@pytest.fixture(scope="module")
def matrix():
    return PreflopMatrix.from_json(preflop_matrix_doc())


def test_matrix_matches_known_equities(matrix):
    i = CLASS_INDEX
    assert matrix.equity[i["AA"], i["KK"]] == pytest.approx(0.82, abs=0.005)
    assert matrix.equity[i["AKs"], i["QQ"]] == pytest.approx(0.462, abs=0.005)
    np.testing.assert_allclose(matrix.equity + matrix.equity.T, 1.0, atol=1e-9)
    vs_random = (matrix.weighted.sum(axis=1) / matrix.count.sum(axis=1))
    assert vs_random[i["AA"]] == pytest.approx(0.852, abs=0.003)
    assert vs_random[i["72o"]] == pytest.approx(0.346, abs=0.003)


def test_heads_up_10bb_matches_published_nash(matrix):
    # Published HU Nash at 10 BB: SB shoves ~58%, BB calls ~37%.
    s = solve_pushfold(matrix, 2, "SB", 10)
    assert CLASS_PRIOR @ (s.push >= 0.5) == pytest.approx(0.58, abs=0.02)
    assert CLASS_PRIOR @ (s.calls["BB"] >= 0.5) == pytest.approx(0.37, abs=0.02)
    assert s.exploitability_bb < 0.01


def test_ranges_tighten_with_depth_and_early_position(matrix):
    widths = [CLASS_PRIOR @ (solve_pushfold(matrix, 2, "SB", s).push >= 0.5) for s in (3, 6, 10, 15, 20)]
    assert widths == sorted(widths, reverse=True)
    by_pos = [CLASS_PRIOR @ (solve_pushfold(matrix, 9, p, 10).push >= 0.5) for p in POSITIONS[9][:-1]]
    assert by_pos == sorted(by_pos)


def test_antes_widen_shoves(matrix):
    plain = CLASS_PRIOR @ (solve_pushfold(matrix, 9, "CO", 10, 0).push >= 0.5)
    ante = CLASS_PRIOR @ (solve_pushfold(matrix, 9, "CO", 10, 0.125).push >= 0.5)
    assert ante > plain


# hand, players, hero, stack BB, ante BB, pusher (None = open shove), expected
SPOTS = [
    ("AsAh", 9, "UTG", 15, 0, None, "push"),
    ("7c2d", 9, "UTG", 10, 0, None, "fold"),
    ("Kh2c", 2, "SB", 10, 0, None, "push"),
    ("Kh2c", 2, "SB", 12, 0, None, "fold"),
    ("Qh2c", 2, "SB", 6, 0, None, "push"),
    ("Qh2c", 2, "SB", 8, 0, None, "fold"),
    ("Ah2d", 6, "BTN", 10, 0, None, "push"),
    ("Ah2d", 9, "UTG", 10, 0, None, "fold"),
    ("8h7h", 6, "CO", 8, 0.125, None, "push"),
    ("8h7h", 9, "UTG1", 8, 0.125, None, "fold"),
    ("5s5d", 9, "UTG", 12, 0.125, None, "push"),
    ("Js9s", 4, "SB", 15, 0, None, "push"),
    ("Kc9d", 3, "BTN", 12, 0, None, "fold"),
    ("Ad7c", 2, "BB", 10, 0, "SB", "call"),
    ("Kd9h", 2, "BB", 10, 0, "SB", "call"),
    ("Td2h", 2, "BB", 10, 0, "SB", "fold"),
    ("AsJd", 9, "BB", 10, 0.125, "UTG", "call"),
    ("AsTd", 6, "BB", 10, 0, "BTN", "call"),
    ("4c4d", 6, "BB", 12, 0, "SB", "call"),
    ("Qs8s", 6, "SB", 15, 0, "BTN", "fold"),
    ("6h6c", 9, "HJ", 7, 0.125, "UTG", "call"),
]


def test_twenty_spots():
    assert len(SPOTS) >= 20


@pytest.mark.parametrize("hand,n,pos,stack,ante,pusher,expected", SPOTS)
def test_lookup_matches_chart_and_solver(matrix, hand, n, pos, stack, ante, pusher, expected):
    d = pushfold_decision(hand, n, pos, stack, ante, pusher)
    assert d.action == expected
    # The stored chart must agree with a fresh solve at the same spot.
    s = solve_pushfold(matrix, n, pusher or pos, stack, ante)
    freq = s.push if pusher is None else s.calls[pos]
    assert (freq[CLASS_INDEX[d.hand_class]] >= 0.5) == (expected != "fold")


def test_chart_covers_every_spot():
    chart = pushfold_chart()
    assert chart["max_exploitability_bb"] < 0.02
    for ante in chart["antes"]:
        for n, seats in POSITIONS.items():
            t = chart["charts"][str(ante)][str(n)]
            assert set(t["push"]) == set(seats[:-1])
            for i, p in enumerate(seats[:-1]):
                assert set(t["call"][p]) == set(seats[i + 1 :])
    aa = CLASS_INDEX["AA"]
    grid = chart["charts"]["0.0"]["9"]["push"]["UTG"]
    assert grid[aa // 13][aa % 13] == chart["max_stack"]
    assert len(CLASSES) == 169


def test_small_stack_uses_smallest_chart_and_ante_snaps():
    d = pushfold_decision("9c4d", 2, "SB", 1.0)
    assert d.action == "push"
    assert pushfold_decision("AsAh", 9, "UTG", 10, ante_bb=0.1).ante_bb == 0.125


def test_lookup_errors():
    with pytest.raises(PushFoldError):
        pushfold_decision("AsAh", 9, "BB", 10)  # nobody behind the BB
    with pytest.raises(PushFoldError):
        pushfold_decision("AsAh", 9, "UTG", 25)  # too deep for push/fold
    with pytest.raises(PushFoldError):
        pushfold_decision("AsAh", 9, "UTG", 10, pusher="BTN")  # pusher acts after hero
    with pytest.raises(PushFoldError):
        pushfold_decision("AsAs", 9, "UTG", 10)
