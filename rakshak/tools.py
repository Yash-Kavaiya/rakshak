"""Tools the Rakshak agent calls once per audio chunk.

`log_call_status` is the heartbeat for every chunk; `raise_scam_alert` fires the
warning. Results are kept in session state so the monitor/UI can read them and
so a call is only alerted once.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

RED_FLAGS: dict[str, str] = {
    "urgency": "Pressure to act right now (deadline, 'only 2 minutes', 'today itself').",
    "threat_or_arrest": "Threats of arrest, FIR, account block, pension stop, jail.",
    "otp_request": "Asks for OTP, PIN, CVV, password or card details.",
    "money_transfer": "Asks to transfer/pay money, 'safe RBI account', fees, UPI.",
    "authority_impersonation": "Claims to be police, CBI, customs, RBI, bank, courier officials.",
    "secrecy_isolation": "Tells victim not to tell family, stay on video call, don't hang up.",
    "remote_app_install": "Asks to install AnyDesk/TeamViewer/APK or click a link.",
    "personal_data_request": "Asks for Aadhaar, PAN, bank account numbers.",
}

SCAM_TYPES = {"digital_arrest", "fake_kyc", "fake_courier", "other"}
RISK_LEVELS = {"safe", "suspicious", "scam"}


def raise_scam_alert(
    scam_type: str,
    red_flags: list[str],
    confidence: float,
    warning_hindi: str,
    warning_gujarati: str,
    evidence: str,
    tool_context: ToolContext,
) -> dict:
    """Warn the user, mid-call, that this call is a scam.

    Args:
        scam_type: One of digital_arrest, fake_kyc, fake_courier, other.
        red_flags: Red-flag ids heard so far, e.g. ["authority_impersonation",
            "threat_or_arrest", "otp_request"]. See the catalogue in your instructions.
        confidence: 0.0-1.0 confidence that this is a scam.
        warning_hindi: 1-2 short, simple Hindi sentences telling the user what to do
            and why (e.g. "पुलिस कभी वीडियो कॉल पर गिरफ्तार नहीं करती। फोन काट दीजिए।").
        warning_gujarati: The same warning in simple Gujarati.
        evidence: Short quote/paraphrase of what the caller said that triggered this.

    Returns:
        Status of the alert.
    """
    # The tool result is the whole answer for this chunk: skip the follow-up LLM
    # call so each chunk costs one model round-trip.
    tool_context.actions.skip_summarization = True
    flags, ignored = [], []
    for flag in red_flags:
        key = flag.strip().lower().replace(" ", "_")
        if key in RED_FLAGS:
            if key not in flags:
                flags.append(key)
        else:
            ignored.append(flag)
    if not flags:
        return {
            "status": "rejected",
            "reason": f"No valid red flags. Use ids from: {sorted(RED_FLAGS)}",
        }

    confidence = max(0.0, min(1.0, float(confidence)))
    existing = tool_context.state.get("alert")
    if existing:
        merged = dict(existing)
        merged["red_flags"] = existing["red_flags"] + [
            f for f in flags if f not in existing["red_flags"]
        ]
        merged["confidence"] = max(existing["confidence"], confidence)
        tool_context.state["alert"] = merged
        return {"status": "already_alerted", "red_flags": merged["red_flags"]}

    alert = {
        "scam_type": scam_type if scam_type in SCAM_TYPES else "other",
        "red_flags": flags,
        "confidence": confidence,
        "warning_hindi": warning_hindi,
        "warning_gujarati": warning_gujarati,
        "evidence": evidence,
        "chunk": tool_context.state.get("current_chunk"),
    }
    tool_context.state["alert"] = alert
    result = {"status": "alert_raised", "red_flags": flags}
    if ignored:
        result["ignored_flags"] = ignored
    return result


def log_call_status(risk_level: str, heard: str, tool_context: ToolContext) -> dict:
    """Record what was heard in this chunk and the current risk level.

    Args:
        risk_level: One of safe, suspicious, scam.
        heard: One-line summary (in English) of what was said in this chunk.

    Returns:
        Whether an alert is already active for this call.
    """
    tool_context.actions.skip_summarization = True
    level = risk_level.strip().lower()
    if level not in RISK_LEVELS:
        level = "suspicious"
    log = list(tool_context.state.get("call_log", []))
    log.append(
        {
            "chunk": tool_context.state.get("current_chunk"),
            "risk_level": level,
            "heard": heard,
        }
    )
    tool_context.state["call_log"] = log
    return {"logged": True, "alert_active": "alert" in tool_context.state}
