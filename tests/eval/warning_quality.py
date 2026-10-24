"""`warning_quality` metric: LLM-as-judge on the Hindi/Gujarati warning an elder would see.

Only cases where the agent raised an alert are judged; other cases score 5 (n/a).
"""

import json
import threading

from google import genai
from google.genai import types
from pydantic import BaseModel

_local = threading.local()


def tool_calls(instance) -> list[dict]:
    # Duplicated from scam_decision.py: agents-cli loads each metric file standalone.
    calls = []
    for turn in (instance.get("agent_data") or {}).get("turns", []):
        for event in turn.get("events", []):
            for part in (event.get("content") or {}).get("parts", []) or []:
                if part.get("function_call"):
                    calls.append(part["function_call"])
    return calls


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def _client() -> genai.Client:
    """One client per grading thread (the eval SDK grades on a thread pool)."""
    client = getattr(_local, "client", None)
    if client is None:
        client = _local.client = genai.Client()
    return client


RUBRIC = """You grade a scam warning shown to an elderly Indian phone user mid-call.
Score 1-5. A 5 means ALL of:
- warning_hindi is natural, simple Hindi in Devanagari; warning_gujarati is simple Gujarati script.
- Each is at most two short sentences an elder can grasp instantly (no jargon).
- It says why the call is fake (e.g. police never arrest on video call / banks never ask OTP)
  and what to do now (hang up, don't pay, tell family).
- red_flags correctly name what the caller actually did in the transcript (no invented flags).
Deduct for wrong script/language, long or bureaucratic text, missing action, wrong flags."""


def evaluate(instance):
    alert = next(
        (c for c in tool_calls(instance) if c.get("name") == "raise_scam_alert"), None
    )
    if alert is None:
        return {"score": 5, "explanation": "n/a: no alert raised in this case"}
    prompt = (
        f"{RUBRIC}\n\nCall transcript so far:\n{instance.get('prompt', '')}\n\n"
        f"Alert arguments:\n{json.dumps(alert.get('args', {}), ensure_ascii=False, indent=1)}"
    )
    response = _client().models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_Verdict,
        ),
    )
    verdict = response.parsed
    if verdict is None:
        return {"score": 0, "explanation": response.text or ""}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
