"""Audio helpers: load calls, simulate a phone line, and cut calls into chunks.

Everything is normalised to 16 kHz mono PCM16, the format Gemini handles best
for speech and the format each chunk is sent to the agent in.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioChunk:
    index: int
    start: float
    end: float
    wav_bytes: bytes


def resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resample of int16 PCM."""
    if src_rate == dst_rate:
        return pcm.astype(np.int16)
    n_out = round(len(pcm) * dst_rate / src_rate)
    x_old = np.arange(len(pcm)) / src_rate
    x_new = np.arange(n_out) / dst_rate
    return np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)


def load_wav(path: str | Path) -> np.ndarray:
    """Read a PCM16 wav file and return 16 kHz mono int16 samples."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit PCM wav is supported")
        rate, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return resample(pcm, rate, SAMPLE_RATE)


def to_wav_bytes(pcm: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


def phone_line(pcm: np.ndarray, rate: int, seed: int = 7) -> np.ndarray:
    """Make clean TTS sound like a phone call: 300-3400 Hz band, light hiss, 16 kHz."""
    spectrum = np.fft.rfft(pcm.astype(np.float64))
    freqs = np.fft.rfftfreq(len(pcm), 1 / rate)
    spectrum[(freqs < 300) | (freqs > 3400)] = 0
    band = np.fft.irfft(spectrum, n=len(pcm))
    band += np.random.default_rng(seed).normal(0, 120, len(band))
    band = np.clip(band, -32768, 32767).astype(np.int16)
    return resample(band, rate, SAMPLE_RATE)


def chunk_audio(pcm: np.ndarray, seconds: float = 5.0) -> list[AudioChunk]:
    if seconds <= 0:
        raise ValueError("chunk length must be positive")
    step = int(seconds * SAMPLE_RATE)
    chunks = []
    for i, offset in enumerate(range(0, len(pcm), step)):
        piece = pcm[offset : offset + step]
        chunks.append(
            AudioChunk(
                index=i,
                start=round(offset / SAMPLE_RATE, 3),
                end=round((offset + len(piece)) / SAMPLE_RATE, 3),
                wav_bytes=to_wav_bytes(piece),
            )
        )
    return chunks


def merge_chunks(chunks: list[AudioChunk]) -> AudioChunk:
    """Join consecutive chunks into one (used when analysis lags behind the call)."""
    if len(chunks) == 1:
        return chunks[0]
    pcm = np.concatenate(
        [
            np.frombuffer(wave.open(io.BytesIO(c.wav_bytes)).readframes(-1), np.int16)
            for c in chunks
        ]
    )
    return AudioChunk(
        chunks[0].index, chunks[0].start, chunks[-1].end, to_wav_bytes(pcm)
    )


def chunk_wav(path: str | Path, seconds: float = 5.0) -> list[AudioChunk]:
    return chunk_audio(load_wav(path), seconds)


def duration(path: str | Path) -> float:
    return len(load_wav(path)) / SAMPLE_RATE
