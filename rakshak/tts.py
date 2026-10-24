"""Speak the warning aloud (Gemini TTS) so an elder doesn't have to read the screen."""

from __future__ import annotations

import functools
import os

import numpy as np
from google import genai
from google.genai import types

from rakshak.audio import to_wav_bytes

TTS_MODEL = os.getenv("RAKSHAK_TTS_MODEL", "gemini-2.5-flash-tts")
_STYLE = {
    "hi": "Say this urgently but kindly, like a caring grandchild warning their grandparent, in Hindi:",
    "gu": "Say this urgently but kindly, like a caring grandchild warning their grandparent, in Gujarati:",
}


@functools.cache
def _client() -> genai.Client:
    # Keep one client alive: a throwaway Client() can be garbage-collected (and its
    # HTTP session closed) while the request is still in flight.
    return genai.Client()


@functools.lru_cache(maxsize=64)
def speak(text: str, lang: str = "hi", voice: str = "Kore") -> bytes:
    response = _client().models.generate_content(
        model=TTS_MODEL,
        contents=f"{_STYLE.get(lang, _STYLE['hi'])}\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    pcm = np.frombuffer(response.candidates[0].content.parts[0].inline_data.data, dtype=np.int16)
    return to_wav_bytes(pcm, 24000)
