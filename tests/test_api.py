import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import LLMChoice
from spots import build

SPOTS = {s["id"]: s for s in json.loads((Path(__file__).parent / "fixtures" / "spots_v1.json").read_text())["spots"]}


class SlowHonestLLM:
    """Stands in for Claude with a realistic delay."""

    def explain(self, inp, r):
        time.sleep(1.5)
        return LLMChoice(option_id=r.best_option, explanation=f"{r.hand_description}.")


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "h.sqlite3"), explainer=SlowHonestLLM()))


def body(spot_id):
    return build(SPOTS[spot_id]).model_dump()


def test_analyze_and_history(client):
    r = client.post("/api/analyze", json=body("f32"))
    assert r.status_code == 200
    rec = r.json()
    assert rec["action"] in ("call", "raise") and rec["explanation_source"] == "llm"
    assert len(rec["villains"][0]["grid"]) == 13
    hid = rec["hand_id"]
    hands = client.get("/api/hands").json()
    assert hands[0]["id"] == hid and hands[0]["hero_hand"] == ["Ah", "Kd"]
    assert client.put(f"/api/hands/{hid}/notes", json={"notes": "check-raise?"}).json() == {"ok": True}
    one = client.get(f"/api/hands/{hid}").json()
    assert one["notes"] == "check-raise?" and one["input"]["pot"] == 825
    assert client.delete(f"/api/hands/{hid}").status_code == 200
    assert client.get(f"/api/hands/{hid}").status_code == 404


@pytest.mark.parametrize("spot_id", ["p07", "s23", "f30", "f37", "s51"])
def test_end_to_end_under_four_seconds(client, spot_id):
    t = time.perf_counter()
    r = client.post("/api/analyze", json=body(spot_id))
    elapsed = time.perf_counter() - t
    assert r.status_code == 200
    assert elapsed < 4.0, f"{spot_id} took {elapsed:.2f}s (incl. 1.5 s simulated LLM)"


def test_validation_errors_are_422(client):
    bad = body("f32")
    bad["board"] = ["Kh", "7c"]
    assert client.post("/api/analyze", json=bad).status_code == 422
    bad = body("f32")
    bad["hero_hand"] = ["Kh", "Kd"]  # Kh is on the board
    assert client.post("/api/analyze", json=bad).status_code == 422


def test_equity_endpoint(client):
    r = client.post("/api/equity", json={"hero": "AsAh", "villains": ["KK"]}).json()
    assert abs(r["equity"] - 0.82) < 0.01
    assert client.post("/api/equity", json={"hero": "AsAs", "villains": ["KK"]}).status_code == 422


def test_icm_endpoint(client):
    r = client.post("/api/icm", json={"stacks": [5000, 3000, 2000], "payouts": [50, 30, 20], "hero": 0, "villain": 1}).json()
    assert [round(x, 2) for x in r["equity"]] == [38.39, 32.75, 28.86]
    assert r["bubble_factor"] > 1
    assert client.post("/api/icm", json={"stacks": [], "payouts": [50]}).status_code == 422


def test_health_reports_llm(client):
    assert client.get("/api/health").json() == {"ok": True, "llm": True}
