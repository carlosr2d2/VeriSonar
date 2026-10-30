#!/usr/bin/env python3
"""Descarga modelos STT para operación 100% offline.

Uso (con red, una sola vez):
    python scripts/download_models.py

Después los workers leen /data/models sin internet.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/models")
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
VOSK_NAME = "vosk-model-small-es-0.42"


def download_vosk() -> None:
    dest_dir = ROOT / "vosk"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / VOSK_NAME
    if target.exists():
        print(f"Vosk ya está en {target}")
        return
    zip_path = dest_dir / f"{VOSK_NAME}.zip"
    print(f"Descargando {VOSK_URL}")
    urlretrieve(VOSK_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink(missing_ok=True)
    print(f"Listo: {target}")


def prefetch_whisper() -> None:
    cache = ROOT / "whisper"
    cache.mkdir(parents=True, exist_ok=True)
    # distil-large-v3 es inglés; para ES-LATAM / AMR usamos large-v3.
    size = os.environ.get("WHISPER_MODEL_SIZE", "large-v3").strip() or "large-v3"
    try:
        from faster_whisper import WhisperModel

        print(f"Prefetch Whisper {size} (CPU int8)")
        WhisperModel(size, device="cpu", compute_type="int8", download_root=str(cache))
        print(f"Listo: {cache}")
    except Exception as exc:
        print(f"Whisper no se pre-descargó ({exc}). El worker lo intentará en el primer análisis si hay red.")


if __name__ == "__main__":
    download_vosk()
    prefetch_whisper()
