"""Rakshak demo web app.

  uvicorn rakshak.server:app --port 8080   ->  http://localhost:8080

* Replay a recorded call: the browser plays the .wav while the server feeds the
  same audio to the agent in real time and streams verdicts over SSE.
* Live mic: the browser streams 16 kHz PCM over a WebSocket; every ~5 s of audio
  becomes one agent turn.
"""

from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse

from rakshak.audio import SAMPLE_RATE, AudioChunk, duration, to_wav_bytes
from rakshak.monitor import CallMonitor
from rakshak.tools import RED_FLAGS

ROOT = Path(__file__).resolve().parents[1]
CALLS = ROOT / "data" / "calls"
SCRIPTS = ROOT / "data" / "scripts"
STATIC = Path(__file__).parent / "static"
CHUNK_SECONDS = 5.0
BYTES_PER_SAMPLE = 2  # int16 PCM
# Once the mic stops, a leftover tail shorter than this is too short to judge.
MIN_TAIL_BYTES = SAMPLE_RATE * BYTES_PER_SAMPLE
MAX_SPEAK_CHARS = 400

app = FastAPI(title="Rakshak")


@functools.cache
def monitor() -> CallMonitor:
    """One agent runner per process, built lazily so importing stays cheap."""
    return CallMonitor()


def _call_ids() -> list[str]:
    return sorted(p.stem for p in CALLS.glob("*.wav"))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/calls")
def list_calls() -> list[dict]:
    out = []
    for cid in _call_ids():
        meta_file = SCRIPTS / f"{cid}.json"
        meta = (
            json.loads(meta_file.read_text(encoding="utf-8"))
            if meta_file.exists()
            else {}
        )
        out.append(
            {
                "id": cid,
                "label": meta.get("label", "unknown"),
                "language": meta.get("language", ""),
                "scam_type": meta.get("scam_type", ""),
                "duration": round(duration(CALLS / f"{cid}.wav"), 1),
            }
        )
    return out


@app.get("/api/red_flags")
def red_flags() -> dict:
    return RED_FLAGS


@app.get("/calls/{call_id}.wav")
def call_audio(call_id: str) -> FileResponse:
    if call_id not in _call_ids():
        raise HTTPException(404, "unknown call")
    return FileResponse(CALLS / f"{call_id}.wav", media_type="audio/wav")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/api/monitor/{call_id}")
async def monitor_call(call_id: str, chunk: float = CHUNK_SECONDS) -> StreamingResponse:
    if call_id not in _call_ids():
        raise HTTPException(404, "unknown call")

    async def events():
        yield _sse({"type": "start", "call_id": call_id})
        async for ev in monitor().stream(
            CALLS / f"{call_id}.wav", realtime=True, chunk_seconds=chunk
        ):
            yield _sse(ev)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/speak")
async def speak_warning(text: str, lang: str = "hi") -> Response:
    from rakshak.tts import speak

    text = text.strip()
    if not text:
        raise HTTPException(422, "text must not be blank")
    wav = await asyncio.to_thread(speak, text[:MAX_SPEAK_CHARS], lang)
    media_type = "audio/wav" if wav.startswith(b"RIFF") else "audio/mpeg"
    return Response(wav, media_type=media_type)


def _take_pcm(buffer: bytearray) -> bytes:
    """Drain every whole int16 sample from `buffer`, leaving any odd trailing byte
    in place so the next WebSocket frame completes it instead of shifting the
    sample alignment of the rest of the call."""
    whole = len(buffer) - len(buffer) % BYTES_PER_SAMPLE
    data = bytes(buffer[:whole])
    del buffer[:whole]
    return data


@app.websocket("/ws/listen")
async def listen(ws: WebSocket) -> None:
    """Client sends binary little-endian int16 mono PCM at 16 kHz; text "stop" ends."""
    await ws.accept()
    call = monitor().new_call()
    buffer = bytearray()
    offset = 0.0
    index = 0
    stopped = asyncio.Event()
    step = int(CHUNK_SECONDS * SAMPLE_RATE) * BYTES_PER_SAMPLE

    async def receive():
        try:
            while True:
                msg = await ws.receive()
                if msg.get("bytes"):
                    buffer.extend(msg["bytes"])
                elif msg.get("text") == "stop" or msg["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        stopped.set()

    receiver = asyncio.create_task(receive())
    try:
        while not (stopped.is_set() and len(buffer) < MIN_TAIL_BYTES):
            if len(buffer) < step and not stopped.is_set():
                await asyncio.sleep(0.2)
                continue
            # Take everything heard so far: if the model was slow we catch up in one turn.
            pcm = np.frombuffer(_take_pcm(buffer), dtype=np.int16)
            secs = len(pcm) / SAMPLE_RATE
            chunk = AudioChunk(
                index, round(offset, 2), round(offset + secs, 2), to_wav_bytes(pcm)
            )
            offset += secs
            index += 1
            event = await call.feed(chunk, merged=max(1, round(secs / CHUNK_SECONDS)))
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        await ws.send_text(json.dumps(call.summary(), ensure_ascii=False))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receiver.cancel()
