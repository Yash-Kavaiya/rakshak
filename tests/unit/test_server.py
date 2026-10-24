import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from rakshak import server
from rakshak.monitor import CallMonitor
from tests.unit.fakes import FakeRunner


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_monitor", CallMonitor(runner=FakeRunner(alert_on=1)))
    return TestClient(server.app)


def test_index_and_call_list(client):
    assert "Rakshak" in client.get("/").text
    calls = {c["id"]: c for c in client.get("/api/calls").json()}
    assert {"digital_arrest_hi", "fake_kyc_gu", "fake_courier_hi", "genuine_gu"} <= set(
        calls
    )
    assert calls["genuine_gu"]["label"] == "genuine"
    assert calls["fake_kyc_gu"]["language"] == "gu"
    assert calls["digital_arrest_hi"]["duration"] > 30


def test_call_audio_served_and_unknown_is_404(client):
    r = client.get("/calls/digital_arrest_hi.wav")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert client.get("/calls/nope.wav").status_code == 404
    assert client.get("/api/monitor/nope").status_code == 404


def test_monitor_sse_streams_alert_then_done(client, monkeypatch):
    orig = CallMonitor.stream

    def fast(self, chunks, realtime=False, **kw):  # no wall-clock pacing in tests
        return orig(self, chunks, realtime=False, **kw)

    monkeypatch.setattr(CallMonitor, "stream", fast)
    with client.stream("GET", "/api/monitor/genuine_bank_hi") as r:
        events = [
            json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")
        ]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert kinds[2] == "alert"  # FakeRunner alerts on chunk index 1
    assert events[-1]["verdict"] == "scam"


def test_websocket_live_mic_produces_chunk_events(client):
    pcm = np.zeros(16000 * 11, dtype=np.int16).tobytes()  # 11 s of "speech"
    with client.websocket_connect("/ws/listen") as ws:
        for i in range(0, len(pcm), 3200):
            ws.send_bytes(pcm[i : i + 3200])
        ws.send_text("stop")
        events = []
        while True:
            ev = json.loads(ws.receive_text())
            events.append(ev)
            if ev["type"] == "done":
                break
    assert events[-1]["duration"] == pytest.approx(11, abs=0.01)
    assert sum(1 for e in events if e["type"] in ("chunk", "alert")) >= 1
