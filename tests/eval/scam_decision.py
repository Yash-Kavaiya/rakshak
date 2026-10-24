"""`scam_decision` metric: did the agent pick the expected tool for this point in the call?

Each dataset case carries `EXPECT: <tool>` as its reference. Score 1 when the
agent called exactly that decision tool (raise_scam_alert vs log_call_status).
"""

DECISION_TOOLS = {"raise_scam_alert", "log_call_status"}


def tool_calls(instance) -> list[dict]:
    calls = []
    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []) or []:
                if part.get("function_call"):
                    calls.append(part["function_call"])
    return calls


def expected_tool(instance) -> str:
    parts = ((instance.get("reference") or {}).get("response") or {}).get("parts", [])
    text = " ".join(p.get("text", "") for p in parts)
    return text.split("EXPECT:", 1)[1].strip() if "EXPECT:" in text else ""


def evaluate(instance):
    expected = expected_tool(instance)
    made = [c["name"] for c in tool_calls(instance) if c.get("name") in DECISION_TOOLS]
    ok = made == [expected]
    return {
        "score": 1 if ok else 0,
        "explanation": f"expected {expected}, agent called {made}",
    }
