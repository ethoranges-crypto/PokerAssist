"""Build data/equity/preflop_169.json: equity of every hand class vs every class.

eq[a][b] is the all-in preflop equity of class a against class b, averaged over
all card-compatible combo pairs (ties split). count[a][b] is the number of
class-b combos compatible with one combo of class a. Monte Carlo via eval7's C
routine; eq[b][a] = 1 - eq[a][b] by construction.

Usage: python scripts/build_preflop_matrix.py [iterations]
"""

import json
import sys
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path

import eval7

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.ranges import CLASSES, class_combos  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "equity" / "preflop_169.json"
ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000


def _rep(cls):
    return [eval7.Card(c) for c in class_combos(cls)[0]]


def _pair(args):
    a, b = args
    hero = _rep(CLASSES[a])
    return a, b, eval7.py_hand_vs_range_monte_carlo(hero, eval7.HandRange(CLASSES[b]), [], ITERS)


def _count(a, b):
    hero = set(class_combos(CLASSES[a])[0])
    return sum(1 for c in class_combos(CLASSES[b]) if not hero & set(c))


def main():
    n = len(CLASSES)
    jobs = [(a, b) for a in range(n) for b in range(a + 1, n)]
    eq = [[0.0] * n for _ in range(n)]
    with Pool() as pool:
        for a, b, e in pool.imap_unordered(_pair, jobs, chunksize=64):
            eq[a][b], eq[b][a] = e, 1 - e
    for a in range(n):  # a class against itself splits evenly by symmetry
        eq[a][a] = 0.5
    doc = {
        "version": 1,
        "source": f"eval7 Monte Carlo, {ITERS} iterations per class pair",
        "classes": CLASSES,
        "equity": [[round(x, 5) for x in row] for row in eq],
        "count": [[_count(a, b) for b in range(n)] for a in range(n)],
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
