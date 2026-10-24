from types import SimpleNamespace

from rakshak.tools import RED_FLAGS, log_call_status, raise_scam_alert


def ctx():
    return SimpleNamespace(state={}, actions=SimpleNamespace(skip_summarization=False))


def _alert(tc, **overrides):
    args = {
        "scam_type": "digital_arrest",
        "red_flags": ["authority_impersonation", "threat_or_arrest"],
        "confidence": 0.9,
        "warning_hindi": "पुलिस कभी वीडियो कॉल पर गिरफ्तार नहीं करती।",
        "warning_gujarati": "પોલીસ ક્યારેય વિડિયો કૉલ પર ધરપકડ કરતી નથી.",
        "evidence": "Caller claims CBI arrest warrant",
        "tool_context": tc,
    }
    args.update(overrides)
    return raise_scam_alert(**args)


def test_first_alert_is_stored_in_state():
    tc = ctx()
    result = _alert(tc)
    assert result["status"] == "alert_raised"
    assert tc.state["alert"]["red_flags"] == [
        "authority_impersonation",
        "threat_or_arrest",
    ]
    assert tc.state["alert"]["scam_type"] == "digital_arrest"


def test_second_alert_is_deduplicated_but_merges_new_flags():
    tc = ctx()
    _alert(tc)
    result = _alert(
        tc, red_flags=["money_transfer", "threat_or_arrest"], confidence=0.95
    )
    assert result["status"] == "already_alerted"
    assert tc.state["alert"]["red_flags"] == [
        "authority_impersonation",
        "threat_or_arrest",
        "money_transfer",
    ]
    assert tc.state["alert"]["confidence"] == 0.95


def test_unknown_flags_are_dropped_and_names_normalised():
    tc = ctx()
    result = _alert(tc, red_flags=["OTP_Request", "bad vibes"])
    assert tc.state["alert"]["red_flags"] == ["otp_request"]
    assert result["ignored_flags"] == ["bad vibes"]


def test_alert_without_any_valid_flag_is_rejected():
    tc = ctx()
    result = _alert(tc, red_flags=["nonsense"])
    assert result["status"] == "rejected"
    assert "alert" not in tc.state


def test_unknown_scam_type_and_confidence_are_clamped():
    tc = ctx()
    _alert(tc, scam_type="lottery", confidence=7)
    assert tc.state["alert"]["scam_type"] == "other"
    assert tc.state["alert"]["confidence"] == 1.0


def test_log_call_status_appends_and_reports_alert_state():
    tc = ctx()
    assert log_call_status("safe", "greeting", tool_context=tc)["alert_active"] is False
    _alert(tc)
    result = log_call_status("SCAM", "asks for money", tool_context=tc)
    assert result["alert_active"] is True
    assert [e["risk_level"] for e in tc.state["call_log"]] == ["safe", "scam"]


def test_log_call_status_coerces_unknown_risk():
    tc = ctx()
    log_call_status("meh", "x", tool_context=tc)
    assert tc.state["call_log"][0]["risk_level"] == "suspicious"


def test_red_flag_catalogue_covers_required_signals():
    for flag in [
        "urgency",
        "threat_or_arrest",
        "otp_request",
        "money_transfer",
        "authority_impersonation",
    ]:
        assert flag in RED_FLAGS


def test_tools_skip_llm_summarization_for_low_latency():
    tc = ctx()
    log_call_status("safe", "hi", tool_context=tc)
    assert tc.actions.skip_summarization is True
    tc = ctx()
    _alert(tc)
    assert tc.actions.skip_summarization is True


def test_non_numeric_confidence_does_not_crash_the_turn():
    tc = ctx()
    result = _alert(tc, confidence="high")
    assert result["status"] == "alert_raised"
    assert tc.state["alert"]["confidence"] == 0.0


def test_scam_type_is_normalised():
    tc = ctx()
    _alert(tc, scam_type=" Fake KYC ")
    assert tc.state["alert"]["scam_type"] == "fake_kyc"
