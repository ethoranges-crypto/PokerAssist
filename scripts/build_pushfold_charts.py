"""Build data/pushfold/nash_v1.json from the preflop equity matrix.

For every table size (2-9), open-shove position, ante and stack on the grid,
solve the push/fold equilibrium, then store per-hand thresholds: a hand is
pushed (or called) when the effective stack is <= its threshold in BB.
0 = never on the grid; MAX_STACK = at every stack on the grid ("20+").

Usage: python scripts/build_pushfold_charts.py
"""

import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.positions import POSITIONS  # noqa: E402
from engine.pushfold import PreflopMatrix, solve_pushfold  # noqa: E402

STACKS = [x / 2 for x in range(3, 41)]  # 1.5 .. 20 BB
MAX_STACK = STACKS[-1]
ANTES = [0.0, 0.125]
OUT = ROOT / "data" / "pushfold" / "nash_v1.json"
MATRIX = PreflopMatrix.from_json(json.loads((ROOT / "data/equity/preflop_169.json").read_text()))


def _solve(job):
    ante, n, pusher, stack = job
    s = solve_pushfold(MATRIX, n, pusher, stack, ante)
    return job, s.push >= 0.5, {j: f >= 0.5 for j, f in s.calls.items()}, s.exploitability_bb


def _thresholds(flags_by_stack: dict[float, np.ndarray]) -> list[list[float]]:
    th = np.zeros(169)
    for stack in STACKS:
        th = np.where(flags_by_stack[stack], stack, th)
    return th.reshape(13, 13).tolist()


def main():
    jobs = [
        (ante, n, pusher, stack)
        for ante in ANTES
        for n, seats in POSITIONS.items()
        for pusher in seats[:-1]
        for stack in STACKS
    ]
    push, calls, worst = {}, {}, 0.0
    with Pool() as pool:
        for (ante, n, pusher, stack), p, c, expl in pool.imap_unordered(_solve, jobs, chunksize=8):
            push.setdefault((ante, n, pusher), {})[stack] = p
            for j, f in c.items():
                calls.setdefault((ante, n, pusher, j), {})[stack] = f
            worst = max(worst, expl)

    charts = {}
    for ante in ANTES:
        a = charts.setdefault(str(ante), {})
        for n, seats in POSITIONS.items():
            t = a.setdefault(str(n), {"push": {}, "call": {}})
            for pusher in seats[:-1]:
                t["push"][pusher] = _thresholds(push[(ante, n, pusher)])
                t["call"][pusher] = {
                    j: _thresholds(calls[(ante, n, pusher, j)]) for j in seats[seats.index(pusher) + 1 :]
                }
    doc = {
        "version": 1,
        "model": (
            "Chip-EV push/fold Nash by fictitious play. Folded to the pusher; players behind "
            "call or fold in turn, first call ends the action. Equal effective stacks. "
            "Blinds 0.5/1 BB; ante per player in BB."
        ),
        "threshold_rule": "act when effective stack <= threshold (BB); 0 = never; max = at every grid stack",
        "stack_grid": STACKS,
        "max_stack": MAX_STACK,
        "antes": ANTES,
        "max_exploitability_bb": round(worst, 5),
        "grid_layout": "13x13, ranks AKQJT98765432; diagonal pairs, upper suited, lower offsuit",
        "charts": charts,
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print("wrote", OUT, "max exploitability", worst)


if __name__ == "__main__":
    main()
