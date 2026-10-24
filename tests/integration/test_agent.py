"""Live smoke test: transcript chunks through the real agent via CallMonitor."""

import pytest

from rakshak.audio import AudioChunk
from rakshak.monitor import CallMonitor

pytestmark = pytest.mark.live


def _chunks(n: int) -> list[AudioChunk]:
    return [AudioChunk(i, i * 5.0, i * 5.0 + 5.0, b"") for i in range(n)]


async def test_transcript_scam_alerts_on_decisive_chunk():
    lines = [
        "Caller: Namaste, kya main Sharma ji se baat kar raha hoon?",
        "Caller: Main Mumbai police se bol raha hoon. Aapke Aadhaar se drugs wala parcel pakda gaya hai, "
        "aapke naam arrest warrant hai. Video call pe rahiye, kisi ko mat batana.",
    ]
    events = [e async for e in CallMonitor().stream(_chunks(2), transcripts=lines)]
    assert [e["type"] for e in events] == ["chunk", "alert", "done"]
    assert "authority_impersonation" in events[1]["alert"]["red_flags"]


async def test_transcript_family_call_stays_safe():
    lines = [
        "Son: Haan maa, kal subah doctor ke paas chalenge, main 9 baje aa jaunga.",
        "Son: Aur yaad rakhna, koi phone pe OTP maange to kabhi mat dena. Bank khud branch mein bulata hai.",
    ]
    events = [e async for e in CallMonitor().stream(_chunks(2), transcripts=lines)]
    assert events[-1]["verdict"] == "safe"
