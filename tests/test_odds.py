import pytest

from engine.odds import (
    OddsError,
    call_ev,
    effective_stack,
    pot_odds_ratio,
    required_equity,
    spr,
    to_bb,
)


def test_required_equity():
    # villain bets 50 into 100: pot is now 150, hero calls 50 to win 200
    assert required_equity(pot=150, to_call=50) == pytest.approx(0.25)
    assert required_equity(pot=100, to_call=0) == 0.0


def test_pot_odds_ratio():
    assert pot_odds_ratio(pot=150, to_call=50) == pytest.approx(3.0)
    assert pot_odds_ratio(pot=100, to_call=0) is None


def test_spr():
    assert spr(effective=1000, pot=300) == pytest.approx(3.3333, rel=1e-3)
    with pytest.raises(OddsError):
        spr(effective=1000, pot=0)


def test_effective_stack():
    assert effective_stack(1000, [500, 2000]) == 1000
    assert effective_stack(1000, [500, 800]) == 800
    with pytest.raises(OddsError):
        effective_stack(1000, [])


def test_call_ev_break_even_at_required_equity():
    assert call_ev(equity=0.25, pot=150, to_call=50) == pytest.approx(0.0)
    assert call_ev(equity=0.5, pot=150, to_call=50) == pytest.approx(50.0)
    assert call_ev(equity=0.0, pot=150, to_call=50) == pytest.approx(-50.0)


def test_to_bb():
    assert to_bb(650, big_blind=100) == pytest.approx(6.5)
    with pytest.raises(OddsError):
        to_bb(100, big_blind=0)


@pytest.mark.parametrize("pot,call", [(-1, 10), (100, -5)])
def test_negative_amounts_rejected(pot, call):
    with pytest.raises(OddsError):
        required_equity(pot, call)
