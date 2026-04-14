"""Text-to-speech generation using edge-tts (Microsoft, free)."""

from __future__ import annotations

import os
import time
import uuid

import edge_tts
from loguru import logger

_TTS_DIR = "/tmp/kaia_tts"
_MAX_TEXT_LENGTH = 2000
_CLEANUP_AGE_SECONDS = 3600  # 1 hour


async def text_to_speech(
    text: str,
    voice: str = "en-US-AriaNeural",
    output_path: str | None = None,
) -> str | None:
    """Generate speech audio from text using edge-tts.

    Args:
        text: Text to convert to speech.
        voice: edge-tts voice name.
        output_path: Optional output file path. Auto-generated if None.

    Returns:
        Path to generated .mp3 file, or None on failure.
    """
    if not text or not text.strip():
        return None

    # Truncate long text
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH] + "..."

    try:
        # Ensure output directory exists
        os.makedirs(_TTS_DIR, exist_ok=True)

        if output_path is None:
            output_path = os.path.join(_TTS_DIR, f"tts_{uuid.uuid4().hex[:12]}.mp3")

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

        logger.debug("TTS generated: {} ({} chars)", output_path, len(text))
        return output_path

    except Exception as exc:
        logger.error("TTS generation failed: {}", exc)
        return None


def cleanup_old_files() -> int:
    """Remove TTS files older than 1 hour. Returns count of files removed."""
    if not os.path.exists(_TTS_DIR):
        return 0

    removed = 0
    cutoff = time.time() - _CLEANUP_AGE_SECONDS
    for filename in os.listdir(_TTS_DIR):
        filepath = os.path.join(_TTS_DIR, filename)
        try:
            if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                removed += 1
        except OSError:
            pass

    if removed:
        logger.debug("Cleaned up {} old TTS files", removed)
    return removed


def safe_delete(file_path: str) -> None:
    """Delete a file, ignoring errors."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
