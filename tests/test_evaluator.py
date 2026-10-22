"""The built-in evaluator must rank hands exactly like treys (independent reference)."""

import random

import pytest
from treys import Card, Evaluator

from engine import evaluator as E
from engine.cards import DECK

TREYS_NAMES = {
    "Royal Flush": "Straight Flush", "Straight Flush": "Straight Flush", "Four of a Kind": "Quads",
    "Full House": "Full House", "Flush": "Flush", "Straight": "Straight", "Three of a Kind": "Trips",
    "Two Pair": "Two Pair", "Pair": "Pair", "High Card": "High Card",
}
_treys = Evaluator()


def treys_rank(cards):  # lower is better in treys
    return _treys.evaluate([Card.new(c) for c in cards[2:]], [Card.new(c) for c in cards[:2]])


@pytest.mark.parametrize(
    "cards,kind",
    [
        ("As Ks Qs Js Ts 2d 3c", "Straight Flush"),
        ("5h 4h 3h 2h Ah Kd Kc", "Straight Flush"),
        ("9c 9d 9h 9s 2c 3d", "Quads"),
        ("Kc Kd Kh 2s 2c", "Full House"),
        ("Kc Kd Kh 2s 2c 2d Ah", "Full House"),
        ("Ah 9h 7h 4h 2h Kd", "Flush"),
        ("Ad 2c 3h 4s 5d Kc Qc", "Straight"),
        ("7c 7d 7h As 2c", "Trips"),
        ("Ac Ad Kc Kd Qs Qh 2c", "Two Pair"),
        ("Ac Ad 9c 8d 2s", "Pair"),
        ("Ac Jd 9c 8d 2s 3h 4c", "High Card"),
    ],
)
def test_categories(cards, kind):
    assert E.handtype(E.evaluate_strs(cards.split())) == kind


def test_kickers_and_wheel():
    s = E.evaluate_strs
    assert s("Ac Ad Kc 8d 2s".split()) > s("Ac Ad Qc Jd Ts".split())
    assert s("6c 5d 4h 3s 2c".split()) > s("5c 4d 3h 2s Ac".split())  # 6-high beats the wheel
    assert s("Ac Kc Qc Jc 9c".split()) > s("Kd Qd Jd Td 8d".split())
    assert s("2c 2d 2h 3s 3c Ad Ah".split()) == s("2c 2d 2h Ad Ah 4s 5c".split())  # 222AA either way


@pytest.mark.parametrize("n_cards", [5, 6, 7])
def test_matches_treys_on_random_hands(n_cards):
    rng = random.Random(n_cards)
    hands = [rng.sample(DECK, n_cards) for _ in range(4000)]
    ours = [E.evaluate_strs(h) for h in hands]
    theirs = [treys_rank(h) for h in hands]
    for h, a, b in zip(hands, ours, theirs):
        assert E.handtype(a) == TREYS_NAMES[_treys.class_to_string(_treys.get_rank_class(b))], h
    for i in range(len(hands) - 1):
        assert (ours[i] > ours[i + 1]) == (theirs[i] < theirs[i + 1])
        assert (ours[i] == ours[i + 1]) == (theirs[i] == theirs[i + 1])
