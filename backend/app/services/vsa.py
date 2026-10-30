"""Puntaje VSA por clip frente a la línea base de control del mismo evaluado.

El 8–12 Hz se trata como microtemblor vocal: en el protocolo clásico esa banda
está presente en habla relajada y se atenúa con estrés. El puntaje de ítem es
más alto cuando hay menos micro-oscilación, más riesgo acústico y más carga
lingüística en la respuesta. Un ítem relevante se marca si supera la media de
los controles del mismo examen.
"""

from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.signal import welch

from app.core.logging import get_logger
from app.services.acoustic import acoustic_risk_score, extract_acoustic_features, write_pcm16_wav
from app.services.nlp import linguistic_features, linguistic_risk_score
from app.services.praat_acoustic import extract_praat_features, merge_acoustic_features

logger = get_logger(__name__)

KIND_CONTROL = "control"
KIND_STIMULUS = "stimulus"
KIND_RELEVANT = "relevant"
KIND_LABELS = {
    KIND_CONTROL: "Control",
    KIND_STIMULUS: "Estímulo",
    KIND_RELEVANT: "Relevante",
}

THRESHOLD_RATIO = 1.12
MIN_DELTA = 0.08
FM_RELAXED_RATIO = 0.22

CONTROL_HINTS = (
    "se llama",
    "nació",
    "nacio",
    "sentada",
    "sentado",
    "esta sala",
    "esta usted ahora",
    "está usted ahora",
    "buenos días",
    "buenos dias",
    "entrevista de laboratorio",
    "está dispuesta",
    "esta dispuesta",
    "quiere agregar",
    "trabaja usted",
    "fecha de nacimiento",
    "documento",
    "nacionalidad",
    "ciudad",
    "dónde vive",
    "donde vive",
)
STIMULUS_HINTS = (
    "sabe usted que",
    "sabe que faltan",
    "le informaron",
    "pregunta de estímulo",
    "pregunta de estimulo",
)
RELEVANT_HINTS = (
    "tomó usted",
    "tomo usted",
    "toma usted",
    "mercancía",
    "mercancia",
    "sin registrar",
    "ha robado",
    "a robado",
    "robó",
    "hurto",
    "sustra",
    "ha mentido",
    "a mentido",
    "mentido",
    "vio usted",
    "sacar cajas",
    "bitácora",
    "bitacora",
    "inventario",
    "sin firmar",
)

_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", (text or "").lower().replace("¿", " ").replace("?", " ")).strip()


def classify_question_kind(question: str) -> str:
    blob = _norm(question)
    if not blob:
        return KIND_CONTROL
    if any(hint in blob for hint in STIMULUS_HINTS):
        return KIND_STIMULUS
    if any(hint in blob for hint in RELEVANT_HINTS):
        return KIND_RELEVANT
    if any(hint in blob for hint in CONTROL_HINTS):
        return KIND_CONTROL
    if "usted" in blob.split()[:12] and any(
        token in blob for token in ("nombre", "llama", "naci", "edad", "trabajo", "vive")
    ):
        return KIND_CONTROL
    if "usted" in blob:
        return KIND_RELEVANT
    return KIND_CONTROL


def _band_energy(freqs: np.ndarray, psd: np.ndarray, lo: float, hi: float) -> float:
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return 0.0
    return float(np.trapezoid(psd[mask], freqs[mask]))


def _band_ratio(signal: np.ndarray, fs: float, lo: float = 8.0, hi: float = 12.0) -> float:
    if signal.size < 16 or fs <= 0:
        return 0.0
    nperseg = int(min(max(16, signal.size // 2), 128))
    freqs, psd = welch(np.asarray(signal, dtype=np.float64), fs=fs, nperseg=nperseg)
    band = _band_energy(freqs, psd, lo, hi)
    full = _band_energy(freqs, psd, 2.0, 20.0)
    if full <= 1e-12:
        return 0.0
    return float(band / full)


def _envelope_series(y: np.ndarray, sr: int, target_fs: float = 100.0) -> tuple[np.ndarray, float]:
    hop = max(1, int(round(sr / target_fs)))
    n = len(y) // hop
    if n < 8:
        return np.array([], dtype=np.float64), target_fs
    env = np.abs(y[: n * hop]).reshape(n, hop).mean(axis=1)
    return env.astype(np.float64), sr / hop


def micro_oscillation_features(y: np.ndarray, sr: int, f0: np.ndarray | None = None) -> dict:
    """Ratio 8–12 Hz del envolvente (y del F0 si hay) y estrés por supresión."""
    env, env_fs = _envelope_series(y, sr)
    env_ratio = _band_ratio(env, env_fs) if env.size else 0.0
    f0_ratio = 0.0
    if f0 is not None:
        voiced = np.asarray(f0, dtype=np.float64)
        voiced = voiced[np.isfinite(voiced)]
        if voiced.size >= 16:
            f0_ratio = _band_ratio(voiced - np.mean(voiced), 100.0)
    tremor = 0.55 * f0_ratio + 0.45 * env_ratio if f0_ratio else env_ratio
    fm_stress = float(np.clip(1.0 - (tremor / FM_RELAXED_RATIO), 0.0, 1.0))
    return {
        "fm_8_12_ratio": round(float(tremor), 4),
        "fm_envelope_ratio": round(float(env_ratio), 4),
        "fm_f0_ratio": round(float(f0_ratio), 4),
        "fm_stress": round(fm_stress, 4),
    }


def _slice_features(y: np.ndarray, sr: int, enable_praat: bool) -> dict:
    if y.size < int(sr * 0.12):
        return {"available": False, "reason": "slice_too_short"}
    tmp_path = None
    try:
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(handle.name)
        handle.close()
        write_pcm16_wav(tmp_path, y.astype(np.float32), sr)
        feat = extract_acoustic_features(tmp_path)
        if enable_praat:
            feat = merge_acoustic_features(feat, extract_praat_features(tmp_path))
        return feat
    except Exception as exc:
        logger.warning("vsa_slice_features_failed", error=str(exc))
        return {"available": False, "reason": str(exc)}
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def score_answer_clip(
    y: np.ndarray,
    sr: int,
    question: str,
    answer: str,
    language: str = "es",
    enable_praat: bool = False,
) -> dict:
    kind = classify_question_kind(question)
    acoustic = _slice_features(y, sr, enable_praat)
    voiced = None
    # extract_acoustic_features no expone el contorno; el FM usa el envolvente.
    fm = micro_oscillation_features(y, sr, f0=voiced)
    ling_feat = linguistic_features(answer or "", language=language)
    ling_score, _ = linguistic_risk_score(ling_feat)
    aco_score, _ = acoustic_risk_score(acoustic)
    vsa_score = 0.40 * fm["fm_stress"] + 0.35 * aco_score + 0.25 * ling_score
    return {
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "fm_stress": fm["fm_stress"],
        "fm_8_12_ratio": fm["fm_8_12_ratio"],
        "fm_envelope_ratio": fm["fm_envelope_ratio"],
        "acoustic_score": round(float(aco_score), 4),
        "linguistic_score": round(float(ling_score), 4),
        "vsa_score": round(float(vsa_score), 4),
        "praat": bool(acoustic.get("praat")),
    }


def apply_baseline(items: list[dict]) -> dict:
    scores = [float(item.get("vsa_score") or 0) for item in items]
    controls = [float(item["vsa_score"]) for item in items if item.get("kind") == KIND_CONTROL]
    if controls:
        baseline = float(np.mean(controls))
    elif scores:
        baseline = float(np.median(scores))
    else:
        baseline = 0.35
    enriched: list[dict] = []
    flagged = 0
    for item in items:
        score = float(item.get("vsa_score") or 0)
        delta = score - baseline
        is_probe = item.get("kind") in {KIND_RELEVANT, KIND_STIMULUS}
        mark = bool(is_probe and score >= baseline * THRESHOLD_RATIO and delta >= MIN_DELTA)
        row = {
            **item,
            "delta": round(delta, 4),
            "flagged": mark,
        }
        if mark:
            flagged += 1
        enriched.append(row)
    relevant = [float(i["vsa_score"]) for i in enriched if i.get("kind") == KIND_RELEVANT]
    vsa_index = float(np.mean(relevant)) if relevant else (float(np.mean(scores)) if scores else 0.0)
    return {
        "baseline": round(baseline, 4),
        "threshold_ratio": THRESHOLD_RATIO,
        "min_delta": MIN_DELTA,
        "control_count": sum(1 for i in enriched if i.get("kind") == KIND_CONTROL),
        "stimulus_count": sum(1 for i in enriched if i.get("kind") == KIND_STIMULUS),
        "relevant_count": sum(1 for i in enriched if i.get("kind") == KIND_RELEVANT),
        "flagged_count": flagged,
        "vsa_index": round(vsa_index, 4),
        "method": "vsa-control-baseline-v1",
        "note": (
            "La línea base es la media de las respuestas de control del mismo evaluado. "
            "Un ítem de estímulo o relevante se marca si supera 12% y 0.08 sobre esa línea."
        ),
        "items": enriched,
    }


def _answer_slice(y: np.ndarray, sr: int, row: dict) -> np.ndarray:
    start = float(row.get("answer_start") or row.get("start") or 0)
    end = float(row.get("answer_end") or row.get("end") or 0)
    pad = 0.04
    i0 = max(0, int((start - pad) * sr))
    i1 = min(len(y), max(i0 + 1, int((end + pad) * sr)))
    return y[i0:i1]


def attach_vsa_scores(
    interview: dict,
    wav_path: str | Path,
    language: str = "es",
    enable_praat: bool = False,
) -> dict:
    import soundfile as sf

    y, sr = sf.read(str(wav_path), always_2d=False)
    if getattr(y, "ndim", 1) > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    rows = interview.get("exchanges") or []
    scored: list[dict] = []
    for row in rows:
        slice_y = _answer_slice(y, sr, row)
        metrics = score_answer_clip(
            slice_y,
            int(sr),
            str(row.get("question") or ""),
            str(row.get("answer") or ""),
            language=language,
            enable_praat=enable_praat,
        )
        item = {
            "index": row.get("index"),
            "question": row.get("question"),
            "answer": row.get("answer"),
            "start": row.get("start"),
            "end": row.get("end"),
            **metrics,
        }
        scored.append(item)
    summary = apply_baseline(scored)
    by_index = {item["index"]: item for item in summary["items"]}
    for row in rows:
        extra = by_index.get(row.get("index")) or {}
        row["kind"] = extra.get("kind")
        row["kind_label"] = extra.get("kind_label")
        row["vsa_score"] = extra.get("vsa_score")
        row["fm_stress"] = extra.get("fm_stress")
        row["fm_8_12_ratio"] = extra.get("fm_8_12_ratio")
        row["acoustic_score"] = extra.get("acoustic_score")
        row["linguistic_score"] = extra.get("linguistic_score")
        row["delta"] = extra.get("delta")
        row["flagged"] = extra.get("flagged")
    interview["vsa"] = summary
    return interview


def allocate_evaluation_code(db) -> str:
    from sqlalchemy import select

    from app.models import AnalysisSession

    year = datetime.now(timezone.utc).year
    prefix = f"VSA-{year}-"
    last = db.scalar(
        select(AnalysisSession.evaluation_code)
        .where(AnalysisSession.evaluation_code.like(f"{prefix}%"))
        .order_by(AnalysisSession.evaluation_code.desc())
        .limit(1)
    )
    serial = 1
    if last:
        try:
            serial = int(str(last).rsplit("-", 1)[-1]) + 1
        except ValueError:
            serial = 1
    return f"{prefix}{serial:04d}"


def exam_from_session(session, evaluator=None) -> dict:
    evaluator_name = getattr(session, "evaluator_name", None) if session else None
    if not evaluator_name and evaluator is not None:
        evaluator_name = getattr(evaluator, "full_name", None)
    if session is None:
        return {}
    return {
        "evaluation_code": session.evaluation_code,
        "title": session.title,
        "subject_name": session.subject_name,
        "subject_document": session.subject_document,
        "location": session.location,
        "modality": session.modality,
        "purpose": session.purpose or session.context,
        "evaluator_name": evaluator_name,
        "evaluator_title": session.evaluator_title,
        "language": session.language,
        "context": session.context,
    }


def flagged_findings(vsa: dict) -> list[dict]:
    findings: list[dict] = []
    baseline = vsa.get("baseline")
    for item in vsa.get("items") or []:
        if not item.get("flagged"):
            continue
        findings.append(
            {
                "code": f"VSA_ITEM_{item.get('index')}",
                "category": "vsa",
                "severity": "alta" if item.get("kind") == KIND_RELEVANT else "media",
                "title": f"Ítem {item.get('index')} sobre la línea base ({item.get('kind_label')})",
                "detail": (
                    f"Puntaje VSA {item.get('vsa_score'):.2f} frente a línea base {baseline:.2f} "
                    f"(Δ {item.get('delta'):+.2f}). Micro-oscilación 8–12 Hz {item.get('fm_8_12_ratio')}."
                ),
                "evidence": str(item.get("question") or "")[:180],
                "weight": round(float(item.get("delta") or 0), 4),
            }
        )
    return findings
