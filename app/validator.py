"""Guards between the LLM and the user.

* The recommended option is always the engine's; an LLM pick that differs is
  overridden and logged.
* Every number in the LLM's explanation must appear in the engine result or
  the hand input (allowing rounding and 0.58 -> 58%); otherwise the text is
  replaced by the deterministic explanation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from engine.schema import EngineResult, HandInput

log = logging.getLogger("pokerassist.validator")

# A number not glued to letters/digits on the left (so "Kh7c", "A9o" are skipped),
# optionally followed by a unit. Numbers in "3-bet", "6-max", "9-handed" are words.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.$])\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?=(%|x|bb|BB|\b))(?![A-Za-z])")
_WORD_SUFFIX = re.compile(r"^-(bet|bets|betting|max|handed|way|card|cards|outer|barrel)", re.I)


def _walk(value, skip: set[str]) -> Iterable[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in skip:
                yield from _walk(v, skip)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v, skip)
    elif isinstance(value, str):
        for m in re.finditer(r"\d+(?:\.\d+)?", value):
            yield float(m.group())


def allowed_numbers(inp: HandInput, result: EngineResult) -> set[float]:
    raw = set(_walk(result.model_dump(), skip={"grid"})) | set(_walk(inp.model_dump(), skip=set()))
    out = set()
    for x in raw:
        variants = {x, round(x), round(x, 1), round(x, 2), abs(x), round(abs(x), 1), round(abs(x), 2)}
        if abs(x) <= 1.5:  # fractions are often quoted as percentages
            variants |= {round(100 * x), round(100 * x, 1), round(100 * abs(x)), round(100 * abs(x), 1)}
        out |= {float(v) for v in variants}
    return out


def numbers_in(text: str) -> list[tuple[str, float]]:
    found = []
    for m in _NUMBER.finditer(text):
        if _WORD_SUFFIX.match(text[m.end():]):
            continue
        token = m.group(0)
        value = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        found.append((token, value))
    return found


def unsupported_numbers(text: str, allowed: set[float]) -> list[str]:
    bad = []
    for token, v in numbers_in(text):
        if not any(abs(v - a) <= 0.051 or (a and abs(v - a) / abs(a) < 0.006) for a in allowed):
            bad.append(token)
    return bad
