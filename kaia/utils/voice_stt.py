"""Speech-to-text transcription using Groq Whisper API."""

from __future__ import annotations

import httpx
from loguru import logger

from config.settings import get_settings

_GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_WHISPER_MODEL = "whisper-large-v3-turbo"
_TIMEOUT = 30  # seconds — audio processing takes longer


async def transcribe_voice(file_path: str) -> str | None:
    """Transcribe an audio file using Groq Whisper API.

    Args:
        file_path: Path to the audio file (.ogg, .mp3, .wav, .m4a).

    Returns:
        Transcribed text string, or None if transcription fails.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        logger.warning("Groq API key not configured — voice transcription unavailable")
        return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    _GROQ_WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    files={"file": (file_path.split("/")[-1], f, "audio/ogg")},
                    data={"model": _WHISPER_MODEL},
                )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("text", "").strip()
        if not text:
            logger.warning("Whisper returned empty transcription for {}", file_path)
            return None

        logger.info("Transcribed {} chars from {}", len(text), file_path)
        return text

    except Exception as exc:
        logger.error("Voice transcription failed for {}: {}", file_path, exc)
        return None
