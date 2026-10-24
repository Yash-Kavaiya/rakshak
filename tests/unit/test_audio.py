import io
import wave

import numpy as np
import pytest

from rakshak.audio import (
    SAMPLE_RATE,
    chunk_audio,
    chunk_wav,
    load_wav,
    merge_chunks,
    phone_line,
    resample,
    to_wav_bytes,
)


def _write_wav(path, seconds, rate=24000, channels=1):
    t = np.arange(int(seconds * rate)) / rate
    tone = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    if channels == 2:
        tone = np.stack([tone, tone], axis=1).reshape(-1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(tone.tobytes())


def test_load_wav_resamples_to_16k_mono(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, 2.0, rate=24000, channels=2)
    pcm = load_wav(p)
    assert pcm.dtype == np.int16
    assert abs(len(pcm) - 2 * SAMPLE_RATE) <= 1


def test_chunk_wav_splits_into_fixed_windows_with_short_tail(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, 12.5)
    chunks = chunk_wav(p, seconds=5)
    assert [c.index for c in chunks] == [0, 1, 2]
    assert [(c.start, c.end) for c in chunks] == [(0.0, 5.0), (5.0, 10.0), (10.0, 12.5)]


def test_chunk_bytes_are_valid_wav(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, 6)
    chunk = chunk_wav(p, seconds=5)[0]
    with wave.open(io.BytesIO(chunk.wav_bytes)) as w:
        assert w.getframerate() == SAMPLE_RATE
        assert w.getnchannels() == 1
        assert w.getnframes() == 5 * SAMPLE_RATE


def test_chunk_audio_rejects_non_positive_window():
    with pytest.raises(ValueError):
        chunk_audio(np.zeros(100, dtype=np.int16), seconds=0)


def test_resample_and_phone_line_keep_duration():
    pcm = (np.random.default_rng(0).standard_normal(24000) * 1000).astype(np.int16)
    assert len(resample(pcm, 24000, 16000)) == 16000
    out = phone_line(pcm, 24000)
    assert len(out) == 16000 and out.dtype == np.int16


def test_to_wav_bytes_roundtrip():
    pcm = np.arange(1600, dtype=np.int16)
    with wave.open(io.BytesIO(to_wav_bytes(pcm))) as w:
        assert np.array_equal(np.frombuffer(w.readframes(1600), np.int16), pcm)


def test_merge_chunks_concatenates_audio_and_spans_time():
    chunks = chunk_audio(np.arange(16000 * 3, dtype=np.int16) % 100, seconds=1)
    merged = merge_chunks(chunks[1:3])
    assert (merged.index, merged.start, merged.end) == (1, 1.0, 3.0)
    with wave.open(io.BytesIO(merged.wav_bytes)) as w:
        assert w.getnframes() == 2 * SAMPLE_RATE
    assert merge_chunks(chunks[:1]) is chunks[0]
