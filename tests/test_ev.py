import pytest

from engine import ev as E


def test_call_ev_break_even_at_pot_odds():
    assert E.call_ev(pot=150, to_call=50, equity=0.25, realize=1.0) == pytest.approx(0)


def test_pure_bluff_at_mdf_is_break_even():
    pot, bet = 100, 50
    fold = 1 - pot / (pot + bet)  # villain folds exactly the bluff break-even
    r = E.Response("BB", fold, equity=0.0, hero_risk=bet, villain_adds=bet, realize=1.0)
    ev, fe = E.aggressive_ev(pot, [r])
    assert ev == pytest.approx(0) and fe == pytest.approx(fold)


def test_first_caller_model():
    a = E.Response("SB", 0.5, 1.0, 100, 100, 1.0)
    b = E.Response("BB", 0.5, 0.0, 100, 100, 1.0)
    ev, fe = E.aggressive_ev(10, [a, b])
    # 0.5 SB calls (win 210 - 100), 0.25 BB calls (lose 100), 0.25 all fold (+10)
    assert ev == pytest.approx(0.5 * 110 + 0.25 * -100 + 0.25 * 10)
    assert fe == pytest.approx(0.25)


def test_rake_reduces_winnings():
    rake = E.Rake(0.05, cap=3)
    assert rake.net(100) == 97
    assert rake.net(20) == 19
    assert E.check_ev(100, 1.0, 1.0, rake) == 97


def test_icm_values_and_bust_places():
    t = E.Table({"SB": 1800, "BB": 0}, [65, 35], hero="SB", pot_taker="BB")
    # BB is all-in (0 behind): still alive. Hero losing everything finishes 2nd.
    assert t.value({"SB": -1800, "BB": 2200 + 1800}) == pytest.approx(35)
    assert t.value({"SB": 2200}) == pytest.approx(65)


def test_icm_call_is_worse_than_chip_ev_on_bubble():
    stacks = {"A": 2500, "B": 2500, "C": 2500, "D": 2500}
    t = E.Table(stacks, [50, 30, 20], hero="A", pot_taker="B")
    chip_neutral_equity = 0.5
    called = E.call_dollars(t, pot=2500, to_call=2500, equity=chip_neutral_equity, realize=1.0)
    assert called < E.fold_dollars(t, pot=2500) + 30  # sanity
    assert E.call_dollars(t, 2500, 2500, 0.5, 1.0) < t.value({"A": 1250})  # coin flip loses $ on the bubble
