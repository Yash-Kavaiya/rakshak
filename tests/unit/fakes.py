"""Test doubles shared by unit tests."""

from google.adk.events import Event
from google.genai import types


class FakeRunner:
    """Pretends to be an ADK Runner: alerts on the chunk index given."""

    def __init__(self, alert_on: int | None):
        self.alert_on = alert_on
        self.calls = []

    async def run_async(
        self, *, user_id, session_id, new_message, state_delta=None, **_
    ):
        idx = state_delta["current_chunk"]
        self.calls.append((session_id, idx, new_message))
        if idx == self.alert_on:
            name = "raise_scam_alert"
            args = {
                "scam_type": "digital_arrest",
                "red_flags": ["threat_or_arrest"],
                "confidence": 0.9,
                "warning_hindi": "फोन काटिए",
                "warning_gujarati": "ફોન કાપો",
                "evidence": "arrest",
            }
            response = {"status": "alert_raised", "red_flags": ["threat_or_arrest"]}
        else:
            name, args = (
                "log_call_status",
                {"risk_level": "safe", "heard": f"chunk {idx}"},
            )
            response = {"logged": True, "alert_active": False}
        yield Event(
            author="rakshak",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(function_call=types.FunctionCall(name=name, args=args))
                ],
            ),
        )
        yield Event(
            author="rakshak",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=name, response=response
                        )
                    )
                ],
            ),
        )
        yield Event(
            author="rakshak",
            content=types.Content(role="model", parts=[types.Part(text="ok")]),
        )
