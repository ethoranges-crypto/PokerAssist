import pytest

from engine.positions import PositionError, blind_posted, players_behind, position_index, positions


def test_every_table_size_ends_with_blinds():
    for n in range(2, 10):
        seats = positions(n)
        assert len(seats) == n
        assert seats[-2:] == ("SB", "BB")


def test_heads_up_and_full_ring():
    assert positions(2) == ("SB", "BB")
    assert positions(9)[0] == "UTG"
    assert players_behind(9, "UTG") == 8
    assert players_behind(6, "BTN") == 2


def test_blinds():
    assert blind_posted(6, "SB") == 0.5
    assert blind_posted(6, "BB") == 1.0
    assert blind_posted(6, "BTN") == 0.0
    assert blind_posted(2, "SB") == 0.5


def test_invalid():
    with pytest.raises(PositionError):
        positions(10)
    with pytest.raises(PositionError):
        position_index(4, "UTG")  # no UTG at a 4-handed table
    assert position_index(6, "btn") == 3
