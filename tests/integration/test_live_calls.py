"""End-to-end: real call audio -> Gemini (via ADK) -> mid-call alert. Needs credentials.

Run with: pytest -m live tests/integration/test_live_calls.py
"""

import json
from pathlib import Path

import pytest

from rakshak.monitor import CallMonitor

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {
    p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/scripts").glob("*.json")
}
CALLS = [sid for sid in sorted(SCRIPTS) if (ROOT / "data/calls" / f"{sid}.wav").exists()]

pytestmark = pytest.mark.live


async def _run(call_id: str) -> tuple[dict, list[dict]]:
    events = [e async for e in CallMonitor().stream(ROOT / "data/calls" / f"{call_id}.wav")]
    return events[-1], events


@pytest.mark.parametrize("call_id", [c for c in CALLS if SCRIPTS[c]["label"] == "scam"])
async def test_scam_call_is_flagged_mid_call_with_red_flags(call_id):
    script = SCRIPTS[call_id]
    timing = json.loads((ROOT / "data/calls" / f"{call_id}.timing.json").read_text(encoding="utf-8"))
    done, events = await _run(call_id)

    assert done["verdict"] == "scam", [e.get("heard") for e in events]
    evident_from = timing[script["alert_line"]]["start"]
    # Mid-call: after the scam became audible, while the call still had time left.
    assert evident_from < done["first_alert_at"] < done["duration"]
    assert done["first_alert_at"] <= done["duration"] - 10, "warning should come with time to spare"

    alert = done["alert"]
    assert "authority_impersonation" in alert["red_flags"]
    assert len(set(alert["red_flags"]) & set(script["expected_flags"])) >= 2
    assert any("ऀ" <= ch <= "ॿ" for ch in alert["warning_hindi"]), "Hindi in Devanagari"
    assert any("઀" <= ch <= "૿" for ch in alert["warning_gujarati"]), "Gujarati script"


@pytest.mark.parametrize("call_id", [c for c in CALLS if SCRIPTS[c]["label"] == "genuine"])
async def test_genuine_call_does_not_cry_wolf(call_id):
    done, events = await _run(call_id)
    assert done["verdict"] == "safe", done["alert"]
    assert all(e["type"] != "alert" for e in events)
