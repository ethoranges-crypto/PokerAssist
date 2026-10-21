# PokerAssist

No-Limit Hold'em decision assistant. A deterministic engine does all the poker
math (equity, pot odds, ranges, push/fold, ICM); the Claude API only ranks and
explains options the engine produces. See the build spec for full scope.

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1. Engine core | Card parsing/validation, range notation + 13×13 grid, Monte Carlo / exact equity (heads-up and multiway), pot odds, SPR | **Done** |
| 2. Preflop + SnG | Cash charts (6/9-max), push/fold Nash charts (2–9 handed, ≤20 BB, ante/no ante), ICM + bubble factor | **Done** |
| 3. Postflop + LLM + UI | Board texture, sizing, EV per action, Claude layer, FastAPI, Next.js UI, history | Next |
| 4. Solver (optional) | Heads-up postflop solver wrapper | — |

## Layout

```
engine/      pure functions, no I/O, no LLM calls
  cards.py   card parsing, duplicate/board-size validation, street inference
  ranges.py  range notation (AA, ATs+, TT-77, AKs:0.5, random…) and grid
  equity.py  hero equity vs one or more ranges (exact when small, else MC)
  odds.py    required equity, pot-odds ratio, SPR, effective stack, call EV
  positions.py  seat names and action order for 2-9 players
  icm.py     Malmuth-Harville ICM, bubble factor, ICM required equity to call
  pushfold.py   push/fold Nash solver + chart lookup (shove / call / fold)
  preflop.py cash chart lookup (open, vs open, vs 3-bet) with mixed frequencies
  data.py    cached loaders for /data
data/
  equity/preflop_169.json    169x169 class-vs-class all-in equity matrix
  pushfold/nash_v1.json      push/call thresholds (13x13 grids) per table/position/ante
  ranges/cash_{6max,9max}_v1.json  100BB cash charts
scripts/     regenerate the data files (matrix, then push/fold charts)
tests/       pytest; fixtures/ hold the equity and ICM reference sets
```

## Setup

```bash
pip install -r requirements.txt
pytest
```

```python
from engine.equity import equity
equity("AsKd", ["22+,AJ+,KQ"], board="Ts9s2c").equity   # 0.4503 (exact)
equity("AsAh", ["random", "random"], seed=1).equity      # ~0.735 (Monte Carlo)
```

## Equity accuracy

`tests/fixtures/equity_reference.json` holds 21 spots (preflop, flop, turn,
river, multiway) whose equities were computed by full enumeration with
[`treys`](https://github.com/ihendley/treys), an evaluator independent of the
`eval7` one the engine uses. The engine must match each within ±1% and run in
under 1 s (default 50k Monte Carlo iterations; exact enumeration heads-up when
it is cheaper, which covers turn and river).

## Preflop and SnG

- **ICM** (`engine/icm.py`): exact Malmuth-Harville over subsets. Tested against
  10+ cases computed by brute force over every finishing order (independent
  algorithm); e.g. 5000/3000/2000 at 50/30/20 → 38.39 / 32.75 / 28.86.
- **Push/fold** (`engine/pushfold.py`): chip-EV Nash by fictitious play on the
  equity matrix. Model: folded to the shover, players behind call or fold in
  turn, first call ends the action (no overcalls), equal effective stacks.
  Heads-up 10 BB gives SB shove 58% / BB call 37%, matching published Nash
  charts; max exploitability across all charts < 0.01 BB. Charts store, per
  hand, the largest stack (0.5 BB grid, 1.5–20 BB) it shoves/calls at.
  ICM adjustment of these ranges is applied in Phase 3's EV step.
- **Cash charts** (`data/ranges/`): hand-authored approximations of
  solver-style 100BB ranges (raise-or-fold opens, no SB limps). Other table
  sizes map positions by players behind and are flagged `approximate`.

Regenerate data: `python scripts/build_preflop_matrix.py && python scripts/build_pushfold_charts.py`.

## Notes

- `ANTHROPIC_API_KEY` is read from the environment (Phase 3); never commit keys.
- Pot convention: `pot` includes any bets already made this street;
  `to_call` is the extra amount hero must add.
