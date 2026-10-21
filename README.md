# PokerAssist

No-Limit Hold'em decision assistant. A deterministic engine does all the poker
math (equity, pot odds, ranges, push/fold, ICM); the Claude API only ranks and
explains options the engine produces. See the build spec for full scope.

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1. Engine core | Card parsing/validation, range notation + 13×13 grid, Monte Carlo / exact equity (heads-up and multiway), pot odds, SPR | **Done** |
| 2. Preflop + SnG | Range charts (6/9-max), push/fold Nash tables, ICM | Next |
| 3. Postflop + LLM + UI | Board texture, sizing, EV per action, Claude layer, FastAPI, Next.js UI, history | — |
| 4. Solver (optional) | Heads-up postflop solver wrapper | — |

## Layout

```
engine/      pure functions, no I/O, no LLM calls
  cards.py   card parsing, duplicate/board-size validation, street inference
  ranges.py  range notation (AA, ATs+, TT-77, AKs:0.5, random…) and grid
  equity.py  hero equity vs one or more ranges (exact when small, else MC)
  odds.py    required equity, pot-odds ratio, SPR, effective stack, call EV
data/ranges/ versioned JSON charts (Phase 2)
tests/       pytest; fixtures/equity_reference.json holds the reference spots
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

## Notes

- `ANTHROPIC_API_KEY` is read from the environment (Phase 3); never commit keys.
- Pot convention: `pot` includes any bets already made this street;
  `to_call` is the extra amount hero must add.
