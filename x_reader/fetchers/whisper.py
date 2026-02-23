# -*- coding: utf-8 -*-
"""
Shared audio transcription helpers used by youtube.py and twitter.py.

Transcription strategy:
  1. Local mlx-whisper (Apple Silicon, USE_LOCAL_WHISPER=true)
  2. Groq Whisper API fallback (GROQ_API_KEY required)
"""

import os
import requests
from loguru import logger


def transcribe_local(audio_path: str) -> str:
    """Transcribe audio using mlx-whisper on Apple Silicon. Returns transcript or empty string."""
    try:
        import mlx_whisper
        model = os.getenv("MLX_WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        logger.info(f"[whisper] transcribing locally with {model}")
        result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=model)
        if not isinstance(result, dict):
            logger.warning(f"[whisper] mlx_whisper returned unexpected type: {type(result)}")
            return ""
        text = result.get("text", "").strip()
        logger.info(f"[whisper] local transcription done, {len(text)} chars")
        return text
    except Exception as e:
        logger.warning(f"[whisper] local transcription failed: {e}")
        return ""


def transcribe_via_groq(audio_path: str) -> str:
    """
    Transcribe audio via Groq Whisper API.

    Requires GROQ_API_KEY env var.
    Groq Whisper limit: 25MB audio file.
    Returns transcript text, or empty string if unavailable.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("[whisper] GROQ_API_KEY not set — no Groq transcription available")
        return ""

    file_size = os.path.getsize(audio_path)
    logger.info(f"[whisper] transcribing {file_size // 1024}KB via Groq Whisper...")

    try:
        with open(audio_path, "rb") as f:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(audio_path), f, "audio/mp4")},
                data={"model": "whisper-large-v3", "response_format": "text"},
                timeout=120,
            )
        if response.status_code == 200:
            transcript = response.text.strip()
            logger.info(f"[whisper] Groq transcript: {len(transcript)} chars")
            return transcript
        else:
            logger.warning(f"[whisper] Groq API error: {response.status_code} {response.text[:200]}")
            return ""
    except Exception as e:
        logger.warning(f"[whisper] Groq transcription failed: {e}")
        return ""


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio file, trying local mlx-whisper first if USE_LOCAL_WHISPER=true,
    falling back to Groq Whisper API.
    """
    use_local = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
    if use_local:
        transcript = transcribe_local(audio_path)
        if transcript:
            return transcript
        logger.info("[whisper] local transcription empty, falling back to Groq")
    return transcribe_via_groq(audio_path)
