from pathlib import Path

import numpy as np
import soundfile as sf

from app.services.acoustic import is_canonical_wav, normalize_to_wav, write_pcm16_wav
from app.services.waveform import extract_clip


def _tone(sr: int, seconds: float = 0.35, freq: float = 220.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_stereo_float_wav_becomes_mono_pcm16(tmp_path: Path) -> None:
    src = tmp_path / "stereo_float.wav"
    stereo = np.stack([_tone(44100, freq=220), _tone(44100, freq=330)], axis=1)
    sf.write(src, stereo, 44100, subtype="FLOAT")
    dest = tmp_path / "out.wav"
    normalize_to_wav(src, dest)
    info = sf.info(dest)
    assert info.channels == 1
    assert info.samplerate == 16000
    assert info.subtype == "PCM_16"
    assert is_canonical_wav(dest)


def test_already_wav_is_rewritten_to_pcm16(tmp_path: Path) -> None:
    src = tmp_path / "mono_float.wav"
    sf.write(src, _tone(16000), 16000, subtype="FLOAT")
    dest = tmp_path / "canonical.wav"
    normalize_to_wav(src, dest)
    assert is_canonical_wav(dest)


def test_extract_clip_writes_pcm16(tmp_path: Path) -> None:
    y = _tone(16000, seconds=1.0)
    dest = tmp_path / "clip.wav"
    extract_clip(y, 16000, 0.1, 0.4, dest)
    assert is_canonical_wav(dest)


def test_write_pcm16_downmixes_and_resamples(tmp_path: Path) -> None:
    stereo = np.stack([_tone(48000, freq=180), _tone(48000, freq=240)], axis=1)
    dest = tmp_path / "from_array.wav"
    write_pcm16_wav(dest, stereo, 48000)
    assert is_canonical_wav(dest)
