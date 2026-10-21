import pytest

from engine.cards import (
    CardError,
    parse_card,
    parse_cards,
    street_from_board,
    validate_hand_and_board,
)


def test_parse_card_normalises_case():
    assert parse_card("as") == "As"
    assert parse_card("Td") == "Td"
    assert parse_card("10h") == "Th"


@pytest.mark.parametrize("bad", ["", "A", "Ax", "1s", "AsK", "ZZ"])
def test_parse_card_rejects_garbage(bad):
    with pytest.raises(CardError):
        parse_card(bad)


def test_parse_cards_accepts_string_and_list():
    assert parse_cards("AsKd") == ["As", "Kd"]
    assert parse_cards("As Kd 2c") == ["As", "Kd", "2c"]
    assert parse_cards(["as", "kd"]) == ["As", "Kd"]
    assert parse_cards("") == []


@pytest.mark.parametrize("n,street", [(0, "preflop"), (3, "flop"), (4, "turn"), (5, "river")])
def test_street_from_board(n, street):
    board = ["2c", "3d", "4h", "5s", "6c"][:n]
    assert street_from_board(board) == street


@pytest.mark.parametrize("n", [1, 2, 6])
def test_street_rejects_invalid_board_size(n):
    with pytest.raises(CardError):
        street_from_board(["2c", "3d", "4h", "5s", "6c", "7d"][:n])


def test_validate_rejects_duplicates_across_hand_and_board():
    with pytest.raises(CardError, match="Duplicate"):
        validate_hand_and_board(["As", "Kd"], ["As", "2c", "3d"])


def test_validate_requires_two_hole_cards():
    with pytest.raises(CardError):
        validate_hand_and_board(["As"], [])


def test_validate_returns_normalised_cards():
    hand, board = validate_hand_and_board("asKD", "2c3d4h")
    assert hand == ["As", "Kd"]
    assert board == ["2c", "3d", "4h"]
