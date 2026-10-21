"""EV of each candidate action (chips, and $ under ICM for Sit & Go).

Model: hero bets/raises; villains respond in turn, each folding with an
estimated probability; the first caller ends the action (no overcalls) and the
hand goes to showdown with hero's equity against that caller's continuing range,
scaled by an equity-realisation factor when chips remain behind. All values are
relative to hero folding now (EV(fold) = 0). ``implied`` adds a caller-supplied
estimate of chips a strong hand wins on later streets (chip EV only).
"""

from __future__ import annotations

from dataclasses import dataclass

from .icm import icm


@dataclass(frozen=True)
class Response:
    position: str
    fold_prob: float
    equity: float  # hero equity vs this villain's continuing range
    hero_risk: float  # chips hero puts in if this villain calls (capped by their stack)
    villain_adds: float  # chips this villain adds to call
    realize: float  # equity-realisation factor (1.0 when someone is all-in)
    implied: float = 0.0  # expected chips won on later streets when called


@dataclass(frozen=True)
class Rake:
    pct: float = 0.0
    cap: float | None = None

    def net(self, pot: float) -> float:
        take = pot * self.pct
        if self.cap is not None:
            take = min(take, self.cap)
        return pot - take


NO_RAKE = Rake()


def fold_ev() -> float:
    return 0.0


def check_ev(pot: float, equity: float, realize: float, rake: Rake = NO_RAKE, implied: float = 0.0) -> float:
    return min(1.0, equity * realize) * rake.net(pot) + implied


def call_ev(
    pot: float, to_call: float, equity: float, realize: float, rake: Rake = NO_RAKE, implied: float = 0.0
) -> float:
    return min(1.0, equity * realize) * rake.net(pot + to_call) - to_call + implied


def aggressive_ev(pot: float, responses: list[Response], rake: Rake = NO_RAKE) -> tuple[float, float]:
    """(EV, probability everyone folds) of a bet/raise/shove."""
    ev, reach = 0.0, 1.0
    for r in responses:
        p_call = reach * (1 - r.fold_prob)
        ev += p_call * (
            min(1.0, r.equity * r.realize) * rake.net(pot + r.hero_risk + r.villain_adds) - r.hero_risk + r.implied
        )
        reach *= r.fold_prob
    return ev + reach * rake.net(pot), reach


# --- ICM ($EV) -------------------------------------------------------------


@dataclass(frozen=True)
class Table:
    """Stacks behind for every player, prize payouts, and who takes the pot if hero gives up."""

    stacks: dict[str, float]
    payouts: list[float]
    hero: str
    pot_taker: str  # main villain

    def value(self, deltas: dict[str, float]) -> float:
        """Hero's prize equity after applying chip ``deltas``.

        Players who bust in this hand finish just below everyone still alive
        (sharing those places' payouts if several bust at once).
        """
        names = list(self.stacks)  # a stack of 0 behind is all-in, still alive
        after = {n: max(0.0, self.stacks[n] + deltas.get(n, 0.0)) for n in names}
        if after[self.hero] > 0:
            alive = [n for n in names if after[n] > 0]
            return icm([after[n] for n in alive], self.payouts)[alive.index(self.hero)]
        n_alive = sum(1 for n in names if after[n] > 0)
        n_bust = len(names) - n_alive
        places = self.payouts[n_alive : n_alive + n_bust]
        return sum(places) / n_bust if places else 0.0


def fold_dollars(t: Table, pot: float) -> float:
    return t.value({t.pot_taker: pot})


def check_dollars(t: Table, pot: float, equity: float, realize: float) -> float:
    q = min(1.0, equity * realize)
    return q * t.value({t.hero: pot}) + (1 - q) * t.value({t.pot_taker: pot})


def call_dollars(t: Table, pot: float, to_call: float, equity: float, realize: float) -> float:
    q = min(1.0, equity * realize)
    return q * t.value({t.hero: pot}) + (1 - q) * t.value({t.hero: -to_call, t.pot_taker: pot + to_call})


def aggressive_dollars(t: Table, pot: float, responses: list[Response]) -> float:
    total, reach = 0.0, 1.0
    for r in responses:
        p_call = reach * (1 - r.fold_prob)
        q = min(1.0, r.equity * r.realize)
        win = t.value({t.hero: pot + r.villain_adds, r.position: -r.villain_adds})
        lose = t.value({t.hero: -r.hero_risk, r.position: pot + r.hero_risk})
        total += p_call * (q * win + (1 - q) * lose)
        reach *= r.fold_prob
    return total + reach * t.value({t.hero: pot})
