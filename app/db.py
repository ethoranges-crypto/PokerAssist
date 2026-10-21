"""SQLite hand history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS hands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    input_json TEXT NOT NULL,
    recommendation_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
)
"""


class HandStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._conn() as c:
            c.execute(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, input_json: dict, recommendation_json: dict, notes: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO hands (created_at, input_json, recommendation_json, notes) VALUES (?, ?, ?, ?)",
                (now, json.dumps(input_json), json.dumps(recommendation_json), notes),
            )
            return int(cur.lastrowid)

    def get(self, hand_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM hands WHERE id = ?", (hand_id,)).fetchone()
        return _row(row) if row else None

    def list(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM hands ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def set_notes(self, hand_id: int, notes: str) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE hands SET notes = ? WHERE id = ?", (notes, hand_id)).rowcount > 0

    def delete(self, hand_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM hands WHERE id = ?", (hand_id,)).rowcount > 0


def _row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "input": json.loads(row["input_json"]),
        "recommendation": json.loads(row["recommendation_json"]),
        "notes": row["notes"],
    }
