"""Feeds a call to the Rakshak agent chunk by chunk and reports alerts as they happen."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

from rakshak.audio import AudioChunk, chunk_wav, merge_chunks


def chunk_message(
    index: int,
    start: float,
    end: float,
    audio: bytes | None = None,
    text: str | None = None,
) -> types.Content:
    header = f"[CALL CHUNK {index + 1} | {start:.1f}s-{end:.1f}s]"
    if text is not None:
        return types.Content(
            role="user", parts=[types.Part(text=f"{header}\nTRANSCRIPT: {text}")]
        )
    return types.Content(
        role="user",
        parts=[
            types.Part(text=header),
            types.Part.from_bytes(data=audio, mime_type="audio/wav"),
        ],
    )


def pair_tool_calls(parts: Iterable[types.Part]) -> list[dict]:
    """Match each function call with its response, in call order.

    Returns `{"name", "args", "result"?}` per call. Responses are matched by id,
    falling back to the latest call of the same name when ids are missing.
    """
    calls: dict[str, dict] = {}
    for part in parts:
        if call := part.function_call:
            key = call.id or f"{call.name}#{len(calls)}"
            calls[key] = {"name": call.name, "args": dict(call.args or {})}
        elif response := part.function_response:
            key = response.id if response.id in calls else None
            if key is None:
                key = next(
                    (k for k in reversed(calls) if calls[k]["name"] == response.name),
                    None,
                )
            if key is not None:
                calls[key]["result"] = dict(response.response or {})
    return list(calls.values())


def default_runner() -> InMemoryRunner:
    from rakshak.agent import app

    runner = InMemoryRunner(app=app)
    runner.auto_create_session = True
    return runner


class LiveCall:
    """One call = one ADK session. Feed it chunks as they are heard."""

    def __init__(self, runner, user_id: str = "listener"):
        self.runner = runner
        self.user_id = user_id
        self.session_id = f"call-{uuid.uuid4().hex[:8]}"
        self.alert: dict | None = None
        self.first_alert_at: float | None = None
        self.heard_until = 0.0

    async def _tool_calls(self, index: int, message: types.Content) -> list[dict]:
        parts: list[types.Part] = []
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=self.session_id,
            new_message=message,
            state_delta={"current_chunk": index},
        ):
            if event.content and event.content.parts:
                parts.extend(event.content.parts)
        return pair_tool_calls(parts)

    async def feed(
        self, chunk: AudioChunk, text: str | None = None, merged: int = 1
    ) -> dict:
        """Analyse one chunk; returns an `alert` event the first time a scam is detected,
        otherwise a `chunk` status event."""
        message = chunk_message(
            chunk.index, chunk.start, chunk.end, chunk.wav_bytes, text
        )
        t_req = time.monotonic()
        calls = await self._tool_calls(chunk.index, message)
        self.heard_until = chunk.end
        base = {
            "chunk": chunk.index,
            "start": chunk.start,
            "end": chunk.end,
            "latency": round(time.monotonic() - t_req, 2),
            "merged": merged,
        }
        raised = next(
            (
                c
                for c in calls
                if c["name"] == "raise_scam_alert"
                and c.get("result", {}).get("status") == "alert_raised"
            ),
            None,
        )
        if raised and self.alert is None:
            self.alert = raised["args"]
            self.first_alert_at = chunk.end
            return {"type": "alert", **base, "alert": self.alert}
        status = next((c["args"] for c in calls if c["name"] == "log_call_status"), {})
        return {
            "type": "chunk",
            **base,
            "risk_level": status.get("risk_level", "scam" if self.alert else "unknown"),
            "heard": status.get("heard", ""),
        }

    def summary(self) -> dict:
        return {
            "type": "done",
            "session_id": self.session_id,
            "verdict": "scam" if self.alert else "safe",
            "first_alert_at": self.first_alert_at,
            "alert": self.alert,
            "duration": self.heard_until,
        }


class CallMonitor:
    """Runs a whole recorded call through the agent, chunk by chunk."""

    def __init__(self, runner=None, user_id: str = "listener"):
        self.runner = runner or default_runner()
        self.user_id = user_id

    def new_call(self) -> LiveCall:
        return LiveCall(self.runner, self.user_id)

    async def stream(
        self,
        chunks: Sequence[AudioChunk] | str | Path,
        realtime: bool = False,
        transcripts: Sequence[str] | None = None,
        chunk_seconds: float = 5.0,
    ) -> AsyncIterator[dict]:
        """Yield `chunk`, `alert` and a final `done` event as the call is analysed.

        With realtime=True each chunk is analysed only once it has been "heard"
        (wall clock reaches its end time), mimicking a live call. If analysis
        falls behind, every chunk heard in the meantime is merged into the next
        turn so the agent always catches up to "now".
        """
        if isinstance(chunks, (str, Path)):
            chunks = chunk_wav(chunks, chunk_seconds)
        call = self.new_call()
        began = time.monotonic()
        pending = list(chunks)
        while pending:
            batch = pending[:1]
            if realtime:
                wait = pending[0].end - (time.monotonic() - began)
                if wait > 0:
                    await asyncio.sleep(wait)
                heard_until = time.monotonic() - began
                batch = [c for c in pending if c.end <= heard_until + 1e-3] or batch
            pending = pending[len(batch) :]
            text = (
                " ".join(transcripts[c.index] for c in batch) if transcripts else None
            )
            yield await call.feed(merge_chunks(batch), text, merged=len(batch))
        yield call.summary()
