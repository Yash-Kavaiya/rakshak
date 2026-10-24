"""Render the scripted demo calls in data/scripts/*.json to data/calls/*.wav.

Each line is synthesised separately with Gemini TTS (one voice per speaker) and
the lines are joined with short pauses, so we know exactly when every line is
spoken. That timing is saved next to the wav (`<id>.timing.json`) and is the
ground truth for "the alert came after the scam became evident but before the
call ended". Finally the call is band-limited so it sounds like a phone line.

Run: python scripts/generate_calls.py [script_id ...]
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from rakshak.audio import SAMPLE_RATE, phone_line, to_wav_bytes  # noqa: E402

TTS_MODEL = os.getenv("RAKSHAK_TTS_MODEL", "gemini-2.5-flash-tts")
TTS_RATE = 24000
PAUSE_SECONDS = 0.5
SCRIPTS = ROOT / "data" / "scripts"
CALLS = ROOT / "data" / "calls"


def speak(client: genai.Client, style: str, speaker: str, voice: str, text: str) -> np.ndarray:
    prompt = f"{style}\nYou are the {speaker}. Speak this line naturally, exactly as written:\n{text}"
    for attempt in range(8):
        try:
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                        )
                    ),
                ),
            )
            blob = response.candidates[0].content.parts[0].inline_data
            return np.frombuffer(blob.data, dtype=np.int16)
        except Exception as exc:  # 429 quota / transient network errors
            if attempt == 7:
                raise
            time.sleep(min(60, 5 * 2**attempt) if "429" in str(exc) else 3)
    raise RuntimeError("unreachable")


def render(script: dict, client: genai.Client) -> tuple[bytes, list[dict]]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        clips = list(
            pool.map(
                lambda line: speak(client, script["style"], line[0], script["speakers"][line[0]], line[1]),
                script["lines"],
            )
        )
    pause = np.zeros(int(PAUSE_SECONDS * TTS_RATE), dtype=np.int16)
    pieces, timing, cursor = [pause], [], PAUSE_SECONDS
    for i, ((speaker, text), clip) in enumerate(zip(script["lines"], clips, strict=True)):
        start = cursor
        cursor += len(clip) / TTS_RATE
        timing.append({"line": i, "speaker": speaker, "text": text, "start": round(start, 2), "end": round(cursor, 2)})
        pieces += [clip, pause]
        cursor += PAUSE_SECONDS
    pcm = phone_line(np.concatenate(pieces), TTS_RATE)
    return to_wav_bytes(pcm, SAMPLE_RATE), timing


def main(ids: list[str]) -> None:
    client = genai.Client()
    CALLS.mkdir(parents=True, exist_ok=True)
    for path in sorted(SCRIPTS.glob("*.json")):
        script = json.loads(path.read_text(encoding="utf-8"))
        if ids and script["id"] not in ids:
            continue
        if not ids and (CALLS / f"{script['id']}.timing.json").exists():
            print(f"{script['id']}: already rendered (pass its id to re-render)")
            continue
        wav, timing = render(script, client)
        (CALLS / f"{script['id']}.wav").write_bytes(wav)
        (CALLS / f"{script['id']}.timing.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{script['id']}.wav: {timing[-1]['end'] + PAUSE_SECONDS:.1f}s, {len(timing)} lines")


if __name__ == "__main__":
    main(sys.argv[1:])
