from __future__ import annotations

import math
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from app.core.logging import get_logger

logger = get_logger(__name__)

TARGET_SR = 16000
TARGET_CHANNELS = 1
TARGET_SUBTYPE = "PCM_16"


def _safe_import_librosa():
    try:
        import librosa

        return librosa
    except Exception as exc:  # pragma: no cover - entorno sin audio nativo
        logger.warning("librosa_unavailable", error=str(exc))
        return None


def load_mono(path: str | Path, target_sr: int = TARGET_SR) -> tuple[np.ndarray, int]:
    librosa = _safe_import_librosa()
    if librosa is None:
        raise RuntimeError("librosa no está disponible en este entorno")
    y, sr = librosa.load(str(path), sr=target_sr, mono=True)
    return y.astype(np.float32), sr


def extract_acoustic_features(path: str | Path) -> dict:
    """Extrae pistas acústicas asociadas a estrés y carga cognitiva."""
    librosa = _safe_import_librosa()
    if librosa is None:
        return {
            "available": False,
            "reason": "librosa_unavailable",
            "duration_seconds": 0.0,
            "sample_rate": TARGET_SR,
        }

    y, sr = load_mono(path)
    duration = float(len(y) / sr) if sr else 0.0
    rms = librosa.feature.rms(y=y)[0]
    energy = float(np.mean(rms)) if len(rms) else 0.0
    energy_std = float(np.std(rms)) if len(rms) else 0.0

    pitches, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
    )
    voiced = pitches[~np.isnan(pitches)] if pitches is not None else np.array([])
    pitch_mean = float(np.mean(voiced)) if voiced.size else 0.0
    pitch_std = float(np.std(voiced)) if voiced.size else 0.0
    pitch_range = float(np.ptp(voiced)) if voiced.size else 0.0

    intervals = librosa.effects.split(y, top_db=30)
    speech_samples = int(sum(end - start for start, end in intervals)) if len(intervals) else 0
    speech_ratio = speech_samples / max(len(y), 1)
    pause_ratio = 1.0 - speech_ratio

    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    # Tasa de habla aproximada por onsets
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    speech_rate = float(len(onsets) / duration) if duration > 0 else 0.0

    jitter = _approx_jitter(voiced)
    shimmer = _approx_shimmer(rms)

    return {
        "available": True,
        "duration_seconds": round(duration, 3),
        "sample_rate": sr,
        "energy_mean": round(energy, 5),
        "energy_std": round(energy_std, 5),
        "pitch_mean_hz": round(pitch_mean, 2),
        "pitch_std_hz": round(pitch_std, 2),
        "pitch_range_hz": round(pitch_range, 2),
        "pause_ratio": round(pause_ratio, 4),
        "speech_ratio": round(speech_ratio, 4),
        "zero_crossing_rate": round(zcr, 5),
        "spectral_centroid": round(centroid, 2),
        "speech_rate_onsets": round(speech_rate, 3),
        "jitter_approx": round(jitter, 5),
        "shimmer_approx": round(shimmer, 5),
        "channels": 1,
    }


def acoustic_risk_score(features: dict) -> tuple[float, list[dict]]:
    if not features.get("available"):
        return 0.35, [
            {
                "code": "ACO_UNAVAILABLE",
                "category": "acustico",
                "severity": "info",
                "title": "Análisis acústico limitado",
                "detail": "No se pudieron extraer rasgos de voz. El índice usa sólo pistas lingüísticas.",
                "weight": 0.0,
            }
        ]

    findings: list[dict] = []
    score = 0.2

    pause = features.get("pause_ratio") or 0
    if pause > 0.42:
        w = min(0.22, (pause - 0.42) * 0.8)
        score += w
        findings.append(
            _finding(
                "ACO_PAUSES",
                "Pausas prolongadas",
                "Una proporción alta de silencio puede indicar carga cognitiva o planificación del discurso.",
                f"Pausa {pause:.0%} de la pista",
                w,
                "media" if pause < 0.55 else "alta",
            )
        )

    pitch_std = features.get("pitch_std_hz") or 0
    if pitch_std > 45:
        w = min(0.18, (pitch_std - 45) / 400)
        score += w
        findings.append(
            _finding(
                "ACO_PITCH",
                "Variabilidad tónica elevada",
                "Cambios bruscos de tono se asocian a activación autonómica. No equivalen a mentira.",
                f"Desvío de tono {pitch_std:.1f} Hz",
                w,
                "media",
            )
        )

    jitter_praat = features.get("jitter_local")
    jitter = jitter_praat if jitter_praat is not None else (features.get("jitter_approx") or 0)
    jitter_threshold = 0.015 if jitter_praat is not None else 0.035
    if jitter and jitter > jitter_threshold:
        w = min(0.16, jitter * (4 if jitter_praat is not None else 1))
        score += w
        unit = f"{jitter:.2%}" if jitter_praat is not None else f"{jitter:.3f}"
        findings.append(
            _finding(
                "ACO_JITTER",
                "Inestabilidad de ciclo vocal",
                (
                    "Jitter local de Praat por encima del umbral relajado para habla continua. "
                    "En clínica se mide sobre vocales sostenidas; aquí es una pista, no un diagnóstico."
                    if jitter_praat is not None
                    else "El jitter aproximado está por encima del umbral típico de habla relajada."
                ),
                f"Jitter {unit}",
                w,
                "media",
            )
        )

    shimmer_praat = features.get("shimmer_local")
    if shimmer_praat is not None and shimmer_praat > 0.06:
        w = min(0.1, shimmer_praat)
        score += w
        findings.append(
            _finding(
                "ACO_SHIMMER",
                "Amplitud irregular (shimmer)",
                "Shimmer local de Praat elevado. Puede asociarse a esfuerzo o inestabilidad de intensidad.",
                f"Shimmer {shimmer_praat:.2%}",
                w,
                "baja",
            )
        )

    hnr = features.get("hnr_mean_db")
    if hnr is not None and hnr < 12:
        w = min(0.12, (12 - hnr) / 40)
        score += w
        findings.append(
            _finding(
                "ACO_HNR",
                "Poco componente armónico",
                "HNR (Praat) bajo: más ruido relativo a los armónicos. Típico de voz tensa, soplada o de síntesis.",
                f"HNR {hnr:.1f} dB",
                w,
                "media" if hnr < 8 else "baja",
            )
        )

    intensity_std = features.get("intensity_std_db")
    if intensity_std is not None and intensity_std > 8:
        w = 0.06
        score += w
        findings.append(
            _finding(
                "ACO_INTENSITY",
                "Intensidad irregular",
                "La desviación de intensidad Praat supera 8 dB en la pista.",
                f"σ intensidad {intensity_std:.1f} dB",
                w,
                "baja",
            )
        )

    rate = features.get("speech_rate_onsets") or 0
    if rate and (rate < 1.4 or rate > 5.5):
        w = 0.1
        score += w
        findings.append(
            _finding(
                "ACO_RATE",
                "Ritmo de habla atípico",
                "Aceleración o enlentecimiento respecto a un rango conversacional latinoamericano.",
                f"{rate:.2f} onsets/s",
                w,
                "baja",
            )
        )

    energy_std = features.get("energy_std") or 0
    if energy_std > 0.08:
        w = 0.08
        score += w
        findings.append(
            _finding(
                "ACO_ENERGY",
                "Energía irregular",
                "La intensidad de la voz fluctúa más de lo esperado en un relato fluido.",
                f"σ energía {energy_std:.3f}",
                w,
                "baja",
            )
        )

    return float(min(1.0, max(0.0, score))), findings


def _approx_jitter(voiced: np.ndarray) -> float:
    if voiced.size < 4:
        return 0.0
    diffs = np.abs(np.diff(voiced))
    mean_f = np.mean(voiced) or 1.0
    return float(np.mean(diffs) / mean_f)


def _approx_shimmer(rms: np.ndarray) -> float:
    if rms.size < 4:
        return 0.0
    diffs = np.abs(np.diff(rms))
    mean_a = np.mean(rms) or 1.0
    return float(np.mean(diffs) / mean_a)


def _finding(code: str, title: str, detail: str, evidence: str, weight: float, severity: str) -> dict:
    return {
        "code": code,
        "category": "acustico",
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence": evidence,
        "weight": round(weight, 4),
    }


def is_canonical_wav(path: str | Path, sr: int = TARGET_SR) -> bool:
    try:
        info = sf.info(str(path))
    except Exception:
        return False
    return info.samplerate == sr and info.channels == TARGET_CHANNELS and info.subtype == TARGET_SUBTYPE


def write_pcm16_wav(dest: str | Path, y: np.ndarray, sr: int) -> Path:
    """Escribe WAV mono 16 kHz PCM 16 bits desde un arreglo de muestras."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(y, dtype=np.float32)
    if data.ndim > 1:
        data = np.mean(data, axis=-1).astype(np.float32)
    if sr != TARGET_SR:
        librosa = _safe_import_librosa()
        if librosa is None:
            raise RuntimeError("librosa no está disponible para resamplear a 16 kHz")
        data = librosa.resample(data, orig_sr=sr, target_sr=TARGET_SR).astype(np.float32)
        sr = TARGET_SR
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0:
        data = data / peak
    data = np.clip(data, -1.0, 1.0)
    sf.write(str(dest), data, sr, subtype=TARGET_SUBTYPE)
    return dest


def normalize_to_wav(
    src: str | Path,
    dest: str | Path,
    sr: int = TARGET_SR,
    on_progress: Callable[[int], None] | None = None,
) -> Path:
    """Cualquier formato de entrada → WAV mono 16 kHz PCM 16 bits."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = Path(src)
    if src.resolve() == dest.resolve():
        dest = dest.with_name(f"{dest.stem}.pcm16.wav")

    def report(percent: int) -> None:
        if on_progress:
            on_progress(max(0, min(99, int(percent))))

    last_error: Exception | None = None
    report(2)
    if _ffmpeg_to_wav(src, dest, sr, on_progress=on_progress) and is_canonical_wav(dest, sr):
        if on_progress:
            on_progress(100)
        return dest
    try:
        report(40)
        y, loaded_sr = load_mono(src, target_sr=sr)
        report(75)
        write_pcm16_wav(dest, y, loaded_sr)
        if is_canonical_wav(dest, sr):
            if on_progress:
                on_progress(100)
            return dest
    except Exception as exc:
        last_error = exc
        logger.warning("pcm16_convert_failed", error=str(exc), src=str(src))
    if _pydub_to_wav(src, dest, sr) and is_canonical_wav(dest, sr):
        if on_progress:
            on_progress(100)
        return dest
    raise RuntimeError(
        f"No se pudo convertir {src.name} a WAV mono {sr} Hz PCM 16 bits"
        + (f": {last_error}" if last_error else "")
    )


def _probe_duration_seconds(src: Path) -> float | None:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return float((completed.stdout or "").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None
    return None


def _parse_out_time(value: str) -> float | None:
    parts = value.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return None


def _ffmpeg_to_wav(
    src: Path,
    dest: Path,
    sr: int,
    on_progress: Callable[[int], None] | None = None,
) -> bool:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vn",
        "-ac",
        str(TARGET_CHANNELS),
        "-ar",
        str(sr),
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-nostats",
        "-progress",
        "pipe:1",
        str(dest),
    ]
    duration = _probe_duration_seconds(src) or 0.0
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        logger.warning("ffmpeg_missing")
        return False

    err_chunks: list[str] = []

    def _drain_stderr() -> None:
        if proc.stderr:
            err_chunks.append(proc.stderr.read() or "")

    drain = threading.Thread(target=_drain_stderr, daemon=True)
    drain.start()
    last_percent = -1
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            elapsed = None
            if line.startswith("out_time=") and not line.startswith("out_time_ms") and not line.startswith("out_time_us"):
                elapsed = _parse_out_time(line.split("=", 1)[1])
            if elapsed is None or duration <= 0 or on_progress is None:
                continue
            percent = min(99, int(elapsed / duration * 100))
            if percent > last_percent:
                last_percent = percent
                on_progress(percent)
        code = proc.wait()
    except Exception as exc:
        proc.kill()
        logger.warning("ffmpeg_convert_failed", error=str(exc))
        return False
    drain.join(timeout=2)
    if code == 0 and dest.exists() and dest.stat().st_size > 44:
        return True
    logger.warning("ffmpeg_convert_failed", error="".join(err_chunks)[-400:])
    return False


def _pydub_to_wav(src: Path, dest: Path, sr: int) -> bool:
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(src)
        audio = audio.set_channels(TARGET_CHANNELS).set_frame_rate(sr).set_sample_width(2)
        audio.export(dest, format="wav")
        return dest.exists() and dest.stat().st_size > 44
    except Exception as exc:
        logger.warning("pydub_fallback", error=str(exc), src=str(src))
        return False
