"""Speak the warning aloud so an elder doesn't have to read the screen."""

from __future__ import annotations

import asyncio
import functools
import logging
import os

import numpy as np
from google import genai
from google.genai import types

from rakshak.audio import to_wav_bytes

logger = logging.getLogger(__name__)

TTS_MODEL = os.getenv("RAKSHAK_TTS_MODEL", "gemini-3.8-flash-tts")
_STYLE = {
    "hi": "Say this urgently but kindly, like a caring grandchild warning their grandparent, in Hindi:",
    "gu": "Say this urgently but kindly, like a caring grandchild warning their grandparent, in Gujarati:",
}

_VOICES = {
    "hi": "hi-IN-SwaraNeural",
    "gu": "gu-IN-DhwaniNeural",
}


@functools.cache
def _client() -> genai.Client:
    return genai.Client()


async def _speak_edge_tts(text: str, lang: str = "hi") -> bytes:
    import edge_tts

    voice = _VOICES.get(lang, "hi-IN-SwaraNeural")
    communicate = edge_tts.Communicate(text, voice)
    mp3_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data.extend(chunk["data"])
    return bytes(mp3_data)


@functools.lru_cache(maxsize=64)
def speak(text: str, lang: str = "hi", voice: str = "Kore") -> bytes:
    try:
        response = _client().models.generate_content(
            model=TTS_MODEL,
            contents=f"{_STYLE.get(lang, _STYLE['hi'])}\n{text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice
                        )
                    )
                ),
            ),
        )
        pcm = np.frombuffer(
            response.candidates[0].content.parts[0].inline_data.data, dtype=np.int16
        )
        return to_wav_bytes(pcm, 24000)
    except Exception:
        # Robust fallback to native high-quality Hindi/Gujarati neural voices
        logger.warning("Gemini TTS failed; falling back to Edge TTS", exc_info=True)
        return asyncio.run(_speak_edge_tts(text, lang))
