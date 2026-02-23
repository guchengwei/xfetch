# -*- coding: utf-8 -*-
"""
Local OCR using easyocr — supports URLs and local file paths.

Install: pip install "x-reader[ocr]"
Enable:  USE_LOCAL_OCR=true in .env

easyocr is MPS-accelerated on Apple Silicon and supports 80+ languages
including Chinese (Simplified/Traditional) + English bilingual text.
"""

import os
import tempfile
from loguru import logger
from typing import Optional

# Module-level reader cache — avoid reloading the model on each call
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        logger.info("[OCR] Loading easyocr model (en + ch_sim)...")
        _reader = easyocr.Reader(["en", "ch_sim"], gpu=True)
        logger.info("[OCR] easyocr model loaded")
    return _reader


def extract_text_from_image(source: str) -> str:
    """
    Run OCR on an image URL or local file path.

    Downloads URL to a temp file if needed, then runs easyocr.
    Returns joined OCR text, or "" on ImportError or any failure.
    """
    try:
        reader = _get_reader()
    except ImportError:
        logger.warning("[OCR] easyocr not installed — pip install 'x-reader[ocr]'")
        return ""
    except Exception as e:
        logger.warning(f"[OCR] Failed to load easyocr: {e}")
        return ""

    try:
        if source.startswith("http://") or source.startswith("https://"):
            return _ocr_from_url(reader, source)
        else:
            return _ocr_file(reader, source)
    except Exception as e:
        logger.warning(f"[OCR] extract_text_from_image failed for {source!r}: {e}")
        return ""


def _ocr_from_url(reader, url: str) -> str:
    import requests
    with tempfile.TemporaryDirectory() as tmpdir:
        # Preserve extension for easyocr file-type detection
        ext = os.path.splitext(url.split("?")[0])[-1] or ".jpg"
        img_path = os.path.join(tmpdir, f"image{ext}")
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(img_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return _ocr_file(reader, img_path)


def _ocr_file(reader, path: str) -> str:
    results = reader.readtext(path, detail=0)
    text = " ".join(str(t) for t in results).strip()
    logger.info(f"[OCR] extracted {len(text)} chars from {os.path.basename(path)}")
    return text
