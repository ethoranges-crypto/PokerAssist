"""Loaders for the versioned JSON charts in /data (read once, cached)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=None)
def load_json(relpath: str) -> dict:
    return json.loads((DATA_DIR / relpath).read_text())


def pushfold_chart(version: str = "v1") -> dict:
    return load_json(f"pushfold/nash_{version}.json")


def cash_chart(table: str, version: str = "v1") -> dict:
    return load_json(f"ranges/cash_{table}_{version}.json")


def preflop_matrix_doc() -> dict:
    return load_json("equity/preflop_169.json")
