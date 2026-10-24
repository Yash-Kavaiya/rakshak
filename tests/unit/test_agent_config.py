import json
from pathlib import Path
from types import SimpleNamespace

from google.genai import types

from rakshak.agent import INSTRUCTION, chunk_verdict, root_agent, track_chunk
from rakshak.tools import RED_FLAGS

ROOT = Path(__file__).resolve().parents[2]


def test_agent_exposes_exactly_the_two_call_tools():
    names = sorted(t.__name__ for t in root_agent.tools)
    assert names == ["log_call_status", "raise_scam_alert"]


def test_instruction_lists_every_red_flag_and_key_rules():
    for flag in RED_FLAGS:
        assert f"`{flag}`" in INSTRUCTION
    assert "Do NOT cry wolf" in INSTRUCTION
    assert "EXACTLY ONE tool per chunk" in INSTRUCTION
    assert "पुलिस कभी वीडियो कॉल पर गिरफ्तार नहीं करती" in INSTRUCTION


def test_scripts_cover_required_demo_scenarios():
    scripts = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/scripts").glob("*.json")]
    by_type = {s["scam_type"] for s in scripts if s["label"] == "scam"}
    assert {"digital_arrest", "fake_kyc", "fake_courier"} <= by_type
    assert any(s["label"] == "genuine" for s in scripts)
    for s in scripts:
        assert set(s["expected_flags"]) <= set(RED_FLAGS)
        assert (s["alert_line"] is None) == (s["label"] == "genuine")
        assert {who for who, _ in s["lines"]} <= set(s["speakers"])


def test_transcript_evalsets_expect_one_alert_per_scam_and_none_for_genuine():
    for label, expected_alerts in (("scam", 1), ("genuine", 0)):
        for path in (ROOT / "rakshak/evals/transcript" / label).glob("*.test.json"):
            for case in json.loads(path.read_text(encoding="utf-8"))["eval_cases"]:
                tools = [
                    t["name"]
                    for inv in case["conversation"]
                    for t in inv["intermediate_data"]["tool_uses"]
                ]
                assert tools.count("raise_scam_alert") == expected_alerts, case["eval_id"]


def test_chunk_verdict_reports_alert_raised_in_this_chunk():
    alert = {
        "scam_type": "fake_kyc",
        "warning_hindi": "बैंक OTP नहीं माँगता।",
        "warning_gujarati": "બેંક OTP નથી માંગતી.",
        "red_flags": ["otp_request", "urgency"],
        "chunk": 3,
    }
    ctx = SimpleNamespace(state={"current_chunk": 3, "alert": alert})
    text = chunk_verdict(ctx).parts[0].text
    assert text.startswith("SCAM ALERT (fake_kyc)") and "otp_request, urgency" in text


def test_chunk_verdict_reports_status_after_alert_and_none_without_tools():
    ctx = SimpleNamespace(
        state={
            "current_chunk": 4,
            "alert": {"chunk": 3},
            "call_log": [{"chunk": 4, "risk_level": "scam", "heard": "asks for UPI"}],
        }
    )
    assert chunk_verdict(ctx).parts[0].text == "scam: asks for UPI"
    assert chunk_verdict(SimpleNamespace(state={"current_chunk": 0})) is None


def test_track_chunk_reads_header_from_user_turn():
    ctx = SimpleNamespace(
        state={},
        user_content=types.Content(role="user", parts=[types.Part(text="[CALL CHUNK 7 | 30.0s-35.0s]")]),
    )
    track_chunk(ctx)
    assert ctx.state["current_chunk"] == 6
    ctx = SimpleNamespace(state={}, user_content=types.Content(role="user", parts=[types.Part(text="hi")]))
    track_chunk(ctx)
    assert "current_chunk" not in ctx.state
