"""Medidas fonéticas con Praat (Parselmouth).

Praat: Boersma & Weenink, Universidad de Ámsterdam.
Parselmouth envuelve los algoritmos; la GUI no se usa.
Licencia GPL: tratar como dependencia copyleft si se distribuye el binario.
"""

from __future__ import annotations

import math
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

PITCH_FLOOR = 75.0
PITCH_CEILING = 500.0


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or abs(number) > 1e30:
        return None
    return number


def _round(value: float | None, digits: int) -> float | None:
    number = _finite(value)
    return None if number is None else round(number, digits)


def extract_praat_features(path: str | Path) -> dict:
    """Pitch, HNR, jitter, shimmer, formantes e intensidad vía Praat."""
    try:
        import parselmouth
        from parselmouth.praat import call
    except Exception as exc:
        logger.info("praat_unavailable", error=str(exc))
        return {"available": False, "reason": "parselmouth_missing"}

    try:
        sound = parselmouth.Sound(str(path))
        pitch = sound.to_pitch_ac(time_step=0.01, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
        f0_mean = _round(call(pitch, "Get mean", 0, 0, "Hertz"), 2)
        f0_std = _round(call(pitch, "Get standard deviation", 0, 0, "Hertz"), 2)
        f0_min = _round(call(pitch, "Get minimum", 0, 0, "Hertz", "Parabolic"), 2)
        f0_max = _round(call(pitch, "Get maximum", 0, 0, "Hertz", "Parabolic"), 2)
        pitch_range = _round((f0_max - f0_min) if f0_max is not None and f0_min is not None else None, 2)

        intensity = sound.to_intensity()
        int_mean = _round(call(intensity, "Get mean", 0, 0, "energy"), 2)
        int_std = _round(call(intensity, "Get standard deviation", 0, 0), 2)

        harmonicity = sound.to_harmonicity_cc()
        hnr = _round(call(harmonicity, "Get mean", 0, 0), 2)

        point_process = call(sound, "To PointProcess (periodic, cc)", PITCH_FLOOR, PITCH_CEILING)
        jitter_local = _finite(call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
        jitter_rap = _finite(call(point_process, "Get jitter (rap)", 0, 0, 0.0001, 0.02, 1.3))
        shimmer_local = _finite(
            call([sound, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        )
        shimmer_apq11 = _finite(
            call([sound, point_process], "Get shimmer (apq11)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        )

        formant = sound.to_formant_burg(time_step=0.01, max_number_of_formants=5, maximum_formant=5500)
        f1 = _round(call(formant, "Get mean", 1, 0, 0, "Hertz"), 1)
        f2 = _round(call(formant, "Get mean", 2, 0, 0, "Hertz"), 1)
        f3 = _round(call(formant, "Get mean", 3, 0, 0, "Hertz"), 1)

        n_voiced = int(call(point_process, "Get number of points"))

        return {
            "available": True,
            "engine": "praat",
            "praat": True,
            "pitch_mean_hz": f0_mean,
            "pitch_std_hz": f0_std,
            "pitch_min_hz": f0_min,
            "pitch_max_hz": f0_max,
            "pitch_range_hz": pitch_range,
            "intensity_mean_db": int_mean,
            "intensity_std_db": int_std,
            "hnr_mean_db": hnr,
            "jitter_local": _round(jitter_local, 5),
            "jitter_rap": _round(jitter_rap, 5),
            "shimmer_local": _round(shimmer_local, 5),
            "shimmer_apq11": _round(shimmer_apq11, 5),
            "formant_f1_hz": f1,
            "formant_f2_hz": f2,
            "formant_f3_hz": f3,
            "voiced_pulses": n_voiced,
            "note": (
                "Jitter/shimmer Praat se interpretan con cautela en habla continua; "
                "en clínica se miden sobre vocales sostenidas."
            ),
        }
    except Exception as exc:
        logger.warning("praat_extract_failed", error=str(exc))
        return {"available": False, "reason": str(exc)}


def merge_acoustic_features(librosa_feat: dict, praat_feat: dict) -> dict:
    merged = dict(librosa_feat or {})
    if not praat_feat.get("available"):
        merged["praat"] = False
        merged["acoustic_engine"] = "librosa"
        return merged

    for key, value in praat_feat.items():
        if key in {"available", "reason"}:
            continue
        if value is not None:
            merged[key] = value

    if praat_feat.get("jitter_local") is not None:
        merged["jitter_approx"] = praat_feat["jitter_local"]
    if praat_feat.get("shimmer_local") is not None:
        merged["shimmer_approx"] = praat_feat["shimmer_local"]

    merged["available"] = True
    merged["praat"] = True
    merged["acoustic_engine"] = "praat+librosa"
    return merged
