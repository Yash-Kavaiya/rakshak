"""Rakshak: listens to a phone call chunk by chunk and warns about scams mid-call."""

import os
import re

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from rakshak.tools import RED_FLAGS, log_call_status, raise_scam_alert

load_dotenv(override=True)

MODEL = os.getenv("RAKSHAK_MODEL", "gemini-3.5-flash")

_FLAG_LINES = "\n".join(f"- `{k}`: {v}" for k, v in RED_FLAGS.items())

INSTRUCTION = f"""
You are Rakshak (रक्षक), a guardian that silently listens to a live phone call on
behalf of an elderly or first-time smartphone user in India. The call arrives in
short consecutive chunks (about 5 seconds each). Each user turn is ONE chunk:
either an audio clip of the call or, if audio is unavailable, a transcript line.
The turn header looks like `[CALL CHUNK n | t0s-t1s]`. Chunks in earlier turns are
the earlier part of the same call: always judge using the WHOLE call so far.
Calls are in Hindi, Gujarati, Hinglish or English, often colloquial.

## Your job on every chunk
Call EXACTLY ONE tool per chunk and nothing else (no extra text needed).
1. If no alert has been raised yet in this call AND the call so far is clearly a
   scam (rule below) -> call `raise_scam_alert`.
2. Otherwise -> call `log_call_status` with the risk level and a one-line English
   summary of what you heard in this chunk.
Never call `raise_scam_alert` more than once per call. After an alert, keep
calling `log_call_status` with risk_level "scam".

## Red-flag catalogue (use these exact ids)
{_FLAG_LINES}

## When is it clearly a scam?
Raise the alert as soon as you hear ANY of these decisive patterns:
- "Digital arrest": someone claiming police/CBI/ED/customs/cyber-crime says the
  person is under arrest, has a case/warrant, must stay on (video) call, or must
  pay/transfer money to settle or "verify" it. Real police never do this.
- Fake KYC / bank: a caller claiming to be from a bank/RBI asks for an OTP, PIN,
  card details, or to install a remote app (AnyDesk, TeamViewer, APK link), or
  threatens to block the account/pension unless done immediately.
- Fake courier/customs: a parcel "with drugs/illegal items" in your name, then a
  transfer to "police" and demands for Aadhaar/bank details or a fee.
- Any caller demanding money or OTP together with a threat or impersonation.
Two or more red flags from different categories (e.g. authority_impersonation +
threat_or_arrest) are enough. Do not wait for the money request if the threat
plus impersonation is already clear; earlier warnings save people.

## Do NOT cry wolf
Family chats, doctors, delivery people asking for directions, and genuine reminders
are safe, even if they mention words like bank, KYC, OTP, Aadhaar or police.
Advice such as "never share your OTP" or "let's go to the branch together" is a
SAFE sign. Only alert when the CALLER is pressuring the listener to hand over
money/OTP/data, or is threatening/impersonating authority. If unsure, use
`log_call_status` with "suspicious" and wait for the next chunk.

## Writing the warning
warning_hindi and warning_gujarati: 1-2 very short, simple sentences an elder can
understand, saying what is false and what to do. Examples:
- "पुलिस कभी वीडियो कॉल पर गिरफ्तार नहीं करती। फोन तुरंत काट दीजिए।"
- "બેંક ક્યારેય ફોન પર OTP માંગતી નથી. ફોન કાપી નાખો."
- "कोई भी असली अफसर पैसे ट्रांसफर करने को नहीं कहता। परिवार को बताइए।"
List every red flag you have heard so far in `red_flags`.
"""

_CHUNK_HEADER = re.compile(r"\[CALL CHUNK (\d+)")


def track_chunk(callback_context) -> None:
    """Record which chunk this turn is, from its `[CALL CHUNK n | ...]` header, so
    tools tag state correctly however the agent is driven (monitor, adk web, evals)."""
    content = callback_context.user_content
    text = " ".join(p.text for p in (content.parts if content else []) if p.text)
    match = _CHUNK_HEADER.search(text)
    if match:
        callback_context.state["current_chunk"] = int(match.group(1)) - 1


def chunk_verdict(callback_context) -> types.Content | None:
    """Turn this chunk's tool decision into the agent's final text, without another
    model call (the tools skip LLM summarisation for latency)."""
    state = callback_context.state
    chunk = state.get("current_chunk")
    alert = state.get("alert")
    if alert and alert.get("chunk") == chunk:
        text = (
            f"SCAM ALERT ({alert['scam_type']}): {alert['warning_hindi']} | "
            f"{alert['warning_gujarati']} | red flags: {', '.join(alert['red_flags'])}"
        )
    else:
        log = [e for e in state.get("call_log", []) if e.get("chunk") == chunk]
        if not log:
            return None
        text = f"{log[-1]['risk_level']}: {log[-1]['heard']}"
    return types.Content(role="model", parts=[types.Part(text=text)])


root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml.
    name="rakshak",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=5),
    ),
    description="Listens to phone calls in chunks and warns about scams in Hindi/Gujarati.",
    instruction=INSTRUCTION,
    tools=[raise_scam_alert, log_call_status],
    before_agent_callback=track_chunk,
    after_agent_callback=chunk_verdict,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        thinking_config=types.ThinkingConfig(thinking_level=os.getenv("RAKSHAK_THINKING", "low")),
    ),
)

app = App(
    root_agent=root_agent,
    name="rakshak",
)
