from engine.ranges import combo_count
from engine.villain import action_order_after, estimate_range, hero_in_position, start_stack
from spots import build

BASE = dict(players=6, hero="BB", hand="AhKd", pot=550, hero_stack=9750, stacks=9750, in_hand=["BTN"])
SRP = ["UTG fold", "HJ fold", "CO fold", "BTN raise 250", "SB fold", "BB call"]


def villain_range(**kw):
    inp = build({**BASE, **kw})
    return estimate_range(inp, inp.villains[0])


def test_open_raise_uses_chart_and_dead_cards():
    r, src = villain_range(actions=SRP, board="Kh7c2d")
    assert "open-raise chart" in src
    assert all("Ah" not in c and "Kh" not in c for c in r)


def test_bets_narrow_and_checks_cap():
    base, _ = villain_range(actions=SRP, board="Kh7c2d")
    bet, src = villain_range(actions=SRP + ["flop: BB check", "flop: BTN bet 180"], board="Kh7c2d", pot=730, to_call=180)
    assert combo_count(bet) < 0.75 * combo_count(base)
    assert "flop bet" in src


def test_villain_type_widens_and_tightens():
    tight, _ = villain_range(actions=SRP, board="Kh7c2d", types={"BTN": "tight"})
    loose, _ = villain_range(actions=SRP, board="Kh7c2d", types={"BTN": "loose"})
    base, _ = villain_range(actions=SRP, board="Kh7c2d")
    assert combo_count(tight) < combo_count(base) < combo_count(loose)


def test_no_history_postflop_is_flagged():
    _, src = villain_range(actions=[], board="Kh7c2d")
    assert "default range" in src


def test_three_bet_range_is_narrow():
    inp = build({**BASE, "hero": "CO", "in_hand": ["BTN"], "pot": 1150, "to_call": 500,
                 "actions": ["UTG fold", "HJ fold", "CO raise 250", "BTN raise 750", "SB fold", "BB fold"]})
    r, src = estimate_range(inp, inp.villains[0])
    assert "3-bet chart" in src
    assert combo_count(r) / 1326 < 0.12


def test_positions_and_order():
    inp = build({**BASE, "actions": SRP, "board": "Kh7c2d"})
    assert not hero_in_position(inp)  # BB vs BTN postflop
    assert action_order_after(inp, "BB") == ["BTN"]
    pre = build({**BASE, "hero": "CO", "board": "", "pot": 150, "to_call": 100, "in_hand": ["BTN", "SB", "BB"]})
    assert action_order_after(pre, "CO") == ["BTN", "SB", "BB"]


def test_start_stack_adds_chips_put_in():
    inp = build({**BASE, "actions": SRP + ["flop: BB check", "flop: BTN bet 180"], "board": "Kh7c2d", "pot": 730, "to_call": 180})
    assert start_stack(inp, "BTN") == 9750 + 250 + 180
    assert start_stack(inp, "BB") == 9750 + 250
