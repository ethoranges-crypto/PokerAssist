"""Independent Chip Model (Malmuth-Harville).

The probability a player finishes in a given place is their share of the chips
among players not yet placed. Stacks of 0 are treated as already eliminated, so
payouts apply to the players still in.
"""

from __future__ import annotations

from functools import lru_cache


class ICMError(ValueError):
    pass


def _validate(stacks: list[float], payouts: list[float]) -> None:
    if not stacks:
        raise ICMError("Need at least one stack")
    if any(s < 0 for s in stacks):
        raise ICMError("Stacks must be >= 0")
    if not payouts or any(p < 0 for p in payouts):
        raise ICMError("Need at least one non-negative payout")
    if any(b > a for a, b in zip(payouts, payouts[1:])):
        raise ICMError("Payouts must be non-increasing")


def icm(stacks: list[float], payouts: list[float]) -> list[float]:
    """Prize equity of each stack, in the units of ``payouts``."""
    _validate(stacks, payouts)
    alive = [i for i, s in enumerate(stacks) if s > 0]
    chips = tuple(stacks[i] for i in alive)
    pays = tuple(payouts[: len(alive)])
    n = len(chips)

    @lru_cache(maxsize=None)
    def place(mask: int) -> tuple[float, ...]:
        """Expected winnings of each player in ``mask`` from the remaining places."""
        k = n - bin(mask).count("1")  # index of the next place to award
        out = [0.0] * n
        if k >= len(pays) or mask == 0:
            return tuple(out)
        total = sum(chips[i] for i in range(n) if mask >> i & 1)
        for i in range(n):
            if mask >> i & 1:
                p = chips[i] / total
                out[i] += p * pays[k]
                for j, v in enumerate(place(mask & ~(1 << i))):
                    out[j] += p * v
        return tuple(out)

    values = place((1 << n) - 1)
    result = [0.0] * len(stacks)
    for idx, i in enumerate(alive):
        result[i] = values[idx]
    return result


def _transfer(stacks: list[float], winner: int, loser: int, amount: float) -> list[float]:
    s = list(stacks)
    s[winner] += amount
    s[loser] -= amount
    return s


def bubble_factor(stacks: list[float], payouts: list[float], hero: int, villain: int) -> float:
    """$ lost when hero loses an all-in to villain / $ gained when hero wins it."""
    risk = min(stacks[hero], stacks[villain])
    now = icm(stacks, payouts)[hero]
    win = icm(_transfer(stacks, hero, villain, risk), payouts)[hero]
    lose = icm(_transfer(stacks, villain, hero, risk), payouts)[hero]
    if win == now:
        raise ICMError("Winning gains nothing; bubble factor undefined")
    return (now - lose) / (win - now)


def icm_required_equity(
    stacks: list[float],
    payouts: list[float],
    hero: int,
    villain: int,
    pot: float,
    risk: float,
) -> float:
    """Equity hero needs to call an all-in under ICM.

    ``stacks`` are the stacks if hero folds now. ``pot`` is the dead money hero
    wins besides villain's matched chips (e.g. blinds and antes), already
    removed from the stacks. ``risk`` is what hero puts in to call.
    """
    fold = icm(stacks, payouts)[hero]
    win_stacks = _transfer(stacks, hero, villain, risk)
    win_stacks[hero] += pot
    win = icm(win_stacks, payouts)[hero]
    lose_stacks = _transfer(stacks, villain, hero, risk)
    lose_stacks[villain] += pot
    lose = icm(lose_stacks, payouts)[hero]
    if win <= lose:
        raise ICMError("Winning is not better than losing; check inputs")
    return (fold - lose) / (win - lose)
