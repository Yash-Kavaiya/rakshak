import time

import numpy as np

from rakshak.audio import chunk_audio
from rakshak.monitor import CallMonitor, chunk_message
from tests.unit.fakes import FakeRunner


def _chunks(n):
    return chunk_audio(np.zeros(16000 * 5 * n, dtype=np.int16), seconds=5)


async def _collect(monitor, chunks, **kw):
    return [e async for e in monitor.stream(chunks, **kw)]


async def test_alert_is_emitted_mid_call_and_monitoring_continues():
    runner = FakeRunner(alert_on=2)
    events = await _collect(CallMonitor(runner=runner), _chunks(5))
    kinds = [e["type"] for e in events]
    assert kinds == ["chunk", "chunk", "alert", "chunk", "chunk", "done"]
    alert = events[2]
    assert alert["chunk"] == 2 and alert["start"] == 10.0
    assert alert["alert"]["red_flags"] == ["threat_or_arrest"]
    assert events[-1]["first_alert_at"] == 15.0
    assert events[-1]["verdict"] == "scam"


async def test_genuine_call_never_alerts():
    events = await _collect(CallMonitor(runner=FakeRunner(alert_on=None)), _chunks(3))
    assert all(e["type"] != "alert" for e in events)
    assert events[-1] == {**events[-1], "verdict": "safe", "first_alert_at": None}


async def test_all_chunks_share_one_session_and_carry_audio():
    runner = FakeRunner(alert_on=None)
    await _collect(CallMonitor(runner=runner), _chunks(2))
    assert len({sid for sid, _, _ in runner.calls}) == 1
    msg = runner.calls[0][2]
    assert msg.parts[0].text.startswith("[CALL CHUNK 1 | 0.0s-5.0s]")
    assert msg.parts[1].inline_data.mime_type == "audio/wav"


async def test_rejected_alert_is_not_reported():
    class Rejecting(FakeRunner):
        async def run_async(self, **kw):
            async for ev in super().run_async(**kw):
                for p in ev.content.parts:
                    if p.function_response:
                        p.function_response.response = {"status": "rejected"}
                yield ev

    events = await _collect(CallMonitor(runner=Rejecting(alert_on=0)), _chunks(1))
    assert [e["type"] for e in events] == ["chunk", "done"]


async def test_realtime_mode_waits_for_chunk_to_be_heard():
    chunks = chunk_audio(np.zeros(1600 * 3, dtype=np.int16), seconds=0.1)
    t0 = time.monotonic()
    await _collect(CallMonitor(runner=FakeRunner(alert_on=None)), chunks, realtime=True)
    assert time.monotonic() - t0 >= 0.28


def test_text_chunk_message():
    msg = chunk_message(3, 15.0, 20.0, text="Caller: OTP batao")
    assert msg.parts[0].text == "[CALL CHUNK 4 | 15.0s-20.0s]\nTRANSCRIPT: Caller: OTP batao"


async def test_realtime_mode_merges_chunks_heard_while_analysis_lagged():
    import asyncio

    class SlowRunner(FakeRunner):
        async def run_async(self, **kw):
            await asyncio.sleep(0.25)
            async for ev in super().run_async(**kw):
                yield ev

    runner = SlowRunner(alert_on=None)
    chunks = chunk_audio(np.zeros(1600 * 6, dtype=np.int16), seconds=0.1)
    events = await _collect(CallMonitor(runner=runner), chunks, realtime=True)
    analysed = [e for e in events if e["type"] == "chunk"]
    assert len(analysed) < 6, "lagging analysis should merge chunks"
    assert sum(e["merged"] for e in analysed) == 6
    assert analysed[-1]["end"] == 0.6
