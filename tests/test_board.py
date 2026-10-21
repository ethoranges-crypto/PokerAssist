import pytest

from engine.board import board_texture, describe_hand, draws, range_strengths, top_fraction
from engine.ranges import parse_range, remove_dead


def test_texture():
    dry = board_texture(["Ks", "7d", "2c"])
    assert dry["texture"] == "dry" and dry["suitedness"] == "rainbow" and not dry["paired"]
    wet = board_texture(["Js", "Ts", "9h"])
    assert wet["texture"] == "wet" and wet["straight_possible"] and wet["flush_draw_possible"]
    assert board_texture(["8h", "8d", "2c"])["paired"]
    assert board_texture(["Ah", "7h", "2h"])["suitedness"] == "monotone"
    assert board_texture([]) is None


@pytest.mark.parametrize(
    "hole,board,expected",
    [
        (["As", "Kd"], ["Kh", "7c", "2d"], "top pair"),
        (["Qs", "Qd"], ["Jh", "7c", "2d"], "overpair"),
        (["7s", "7d"], ["7h", "Kc", "2d"], "set"),
        (["7s", "6d"], ["Kh", "7c", "2d"], "second pair"),
        (["As", "5s"], ["Ks", "7s", "2d"], "ace high, flush draw"),
        (["9c", "8c"], ["Th", "7d", "2s"], "high card, open-ended straight draw"),
        (["5c", "4d"], ["Kh", "8s", "7c"], "high card, gutshot"),
        (["Ah", "Kh"], [], "suited (AKs)"),
    ],
)
def test_describe_hand(hole, board, expected):
    assert describe_hand(hole, board) == expected


def test_no_draws_on_river_or_with_made_straight():
    assert not any(draws(["9c", "8c"], ["Th", "7d", "2s", "3h", "4h"]).values())
    assert not draws(["9c", "8c"], ["Th", "7d", "6s"])["oesd"]  # already a straight


def test_strengths_rank_made_hands_and_lift_draws():
    board = ["Kh", "7h", "2d"]
    r = remove_dead(parse_range("KK, 77, AK, 33, Ah5h, QJo"), board)
    s = range_strengths(r, board)
    sets = [s[c] for c in r if c[0][0] == c[1][0] == "K"]
    junk = [s[c] for c in r if c[0][0] == "Q"]
    assert min(sets) > max(junk)
    assert s[("Ah", "5h")] >= 0.65  # nut flush draw continues like a strong hand


def test_top_fraction_keeps_strongest_weight():
    r = parse_range("AA, KK, QQ, JJ")
    s = range_strengths(r, [])
    top = top_fraction(r, s, 0.5)
    assert sum(top.values()) == pytest.approx(12)
    assert {c[0][0] for c in top} == {"A", "K"}
