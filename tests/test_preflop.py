import pytest

from engine.data import cash_chart
from engine.preflop import ChartError, cash_preflop_decision
from engine.ranges import combo_count, parse_range


@pytest.fixture(params=["6max", "9max"])
def chart(request):
    return cash_chart(request.param)


def test_ranges_parse_and_weights_never_exceed_one(chart):
    for e in chart["vs_open"] + chart["vs_3bet"]:
        totals = {}
        for key in ("3bet", "4bet", "call"):
            for c, w in parse_range(e.get(key, "")).items():
                totals[c] = totals.get(c, 0) + w
        assert max(totals.values()) <= 1 + 1e-9, e["hero"]


def test_rfi_widens_towards_the_button(chart):
    seats = chart["seats"][:-2] + ["BTN"]  # SB raise-or-fold is narrower than BTN
    widths = [combo_count(parse_range(chart["rfi"][p])) for p in dict.fromkeys(seats)]
    assert widths == sorted(widths)
    assert 0.08 < widths[0] / 1326 < 0.2  # UTG
    assert 0.4 < combo_count(parse_range(chart["rfi"]["BTN"])) / 1326 < 0.5


def test_every_open_has_exactly_one_response_entry(chart):
    seats = chart["seats"]
    for i, opener in enumerate(seats[:-1]):
        for hero in seats[i + 1 :]:
            hits = [e for e in chart["vs_open"] if hero in e["hero"] and opener in e["openers"]]
            assert len(hits) == 1, (hero, opener)
    for hero in seats[:-1]:
        assert len([e for e in chart["vs_3bet"] if hero in e["hero"]]) == 1, hero


@pytest.mark.parametrize(
    "hand,n,pos,facing,opener,action",
    [
        ("AsKs", 6, "UTG", "none", None, "raise"),
        ("7c2d", 6, "BTN", "none", None, "fold"),
        ("Kd2d", 6, "BTN", "none", None, "raise"),
        ("Kd2d", 6, "UTG", "none", None, "fold"),
        ("9h8h", 9, "UTG", "none", None, "fold"),
        ("9h8h", 9, "CO", "none", None, "raise"),
        ("QsQd", 6, "BB", "open", "BTN", "raise"),
        ("8c8d", 6, "BB", "open", "UTG", "call"),
        ("Js4d", 6, "BB", "open", "UTG", "fold"),
        ("AhKd", 9, "UTG", "3bet", None, "call"),
        ("AhAd", 6, "CO", "3bet", None, "raise"),
        ("Ts9s", 6, "SB", "open", "UTG", "fold"),
        ("Ks5s", 6, "BB", "none", None, "check"),
    ],
)
def test_lookups(hand, n, pos, facing, opener, action):
    d = cash_preflop_decision(hand, n, pos, facing, opener)
    assert d.action == action
    assert sum(d.frequencies.values()) == pytest.approx(1.0)


def test_mixed_frequencies_and_sizes():
    d = cash_preflop_decision("7h6h", 6, "BTN", "open", "CO")
    assert d.frequencies == {"raise": 0.5, "call": 0.5, "fold": 0.0}
    assert d.size_bb == 7.5
    assert cash_preflop_decision("AsKs", 6, "SB").size_bb == 3.0
    assert cash_preflop_decision("AsAh", 6, "BB", "open", "BTN").size_bb == 10.0


def test_short_tables_map_by_players_behind():
    d = cash_preflop_decision("AsKs", 4, "CO")  # 4-handed CO = 6-max CO
    assert d.chart_position == "CO" and d.approximate
    d = cash_preflop_decision("AsKs", 8, "UTG")  # 8-handed UTG = 9-max UTG1
    assert d.chart_position == "UTG1" and d.chart_id == "cash_9max_v1"


def test_errors():
    with pytest.raises(ChartError):
        cash_preflop_decision("AsKs", 6, "UTG", "open", "BTN")  # opener acts after hero
    with pytest.raises(ChartError):
        cash_preflop_decision("AsKs", 6, "BTN", "open")
    with pytest.raises(ChartError):
        cash_preflop_decision("AsKs", 6, "BB", "3bet")
    with pytest.raises(ChartError):
        cash_preflop_decision("AsKs", 6, "BTN", "limp")
