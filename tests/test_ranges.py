import pytest

from engine.ranges import (
    RangeError,
    combo_count,
    hand_class,
    parse_range,
    range_to_grid,
    remove_dead,
)


def classes(r):
    return {hand_class(c) for c in r}


@pytest.mark.parametrize(
    "text,count",
    [
        ("AA", 6),
        ("AKs", 4),
        ("AKo", 12),
        ("AK", 16),
        ("22+", 78),
        ("TT-77", 24),
        ("A2s+", 48),
        ("ATs+", 16),
        ("K9o+", 48),  # K9o, KTo, KJo, KQo
        ("A5s-A2s", 16),
        ("AsKs", 1),
        ("random", 1326),
        ("AA, KK, AKs", 16),
    ],
)
def test_parse_range_combo_counts(text, count):
    assert len(parse_range(text)) == count


def test_plus_on_pairs_and_kickers():
    assert classes(parse_range("QQ+")) == {"AA", "KK", "QQ"}
    assert classes(parse_range("KTs+")) == {"KTs", "KJs", "KQs"}
    assert classes(parse_range("98s-96s")) == {"98s", "97s", "96s"}


def test_weights():
    r = parse_range("AA, AKs:0.5")
    assert r[("As", "Ah")] == 1.0
    assert r[("As", "Ks")] == 0.5
    assert combo_count(r) == pytest.approx(6 + 2)


def test_duplicate_tokens_take_last_weight():
    r = parse_range("AKs, AKs:0.25")
    assert set(r.values()) == {0.25}


@pytest.mark.parametrize("bad", ["AX", "AAs", "A", "22-AKs", "AKs:2", "AKs:-1", "AsAs"])
def test_parse_range_rejects_garbage(bad):
    with pytest.raises(RangeError):
        parse_range(bad)


def test_remove_dead_cards():
    r = remove_dead(parse_range("AA, KK"), ["As", "Kd", "2c"])
    assert len(r) == 3 + 3
    assert all("As" not in c and "Kd" not in c for c in r)


def test_grid_layout():
    grid = range_to_grid(parse_range("AA, AKs, AKo:0.5, 32o"))
    assert len(grid) == 13 and all(len(row) == 13 for row in grid)
    assert grid[0][0] == 1.0  # AA on diagonal
    assert grid[0][1] == 1.0  # AKs above diagonal (row = high card)
    assert grid[1][0] == 0.5  # AKo below diagonal
    assert grid[12][11] == 1.0  # 32o
    assert grid[11][12] == 0.0  # 32s not in range
    assert grid[1][1] == 0.0


def test_grid_partial_class_after_dead_cards():
    r = remove_dead(parse_range("AA"), ["As"])
    assert range_to_grid(r)[0][0] == pytest.approx(3 / 6)
