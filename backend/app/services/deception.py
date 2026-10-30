from __future__ import annotations

from app.core.logging import get_logger
from app.services.acoustic import acoustic_risk_score
from app.services.nlp import linguistic_features, linguistic_risk_score

logger = get_logger(__name__)

DISCLAIMER_ES = (
    "VeriSonar no determina si una persona miente. Estima patrones lingüísticos y "
    "acústicos asociados a carga cognitiva, distanciamiento y estrés. El resultado "
    "es un insumo analítico y no prueba jurídica ni diagnóstico clínico."
)


def combine_scores(linguistic: float, acoustic: float, has_transcript: bool) -> tuple[float, float]:
    if has_transcript:
        deception = 0.58 * linguistic + 0.42 * acoustic
    else:
        deception = 0.25 * linguistic + 0.75 * acoustic
    reliability = 1.0 - deception
    # Suavizado hacia la zona media para evitar falsos extremos con pistas cortas
    deception = 0.15 + 0.7 * deception
    reliability = 1.0 - deception
    return round(float(deception), 4), round(float(reliability), 4)


def band_for(score: float) -> str:
    if score < 0.35:
        return "bajo"
    if score < 0.55:
        return "moderado"
    if score < 0.72:
        return "alto"
    return "crítico"


def analyze_signals(
    transcript: str,
    language: str,
    acoustic_features: dict,
    stt_engine: str,
) -> dict:
    ling_feat = linguistic_features(transcript, language=language)
    ling_score, ling_findings = linguistic_risk_score(ling_feat)
    aco_score, aco_findings = acoustic_risk_score(acoustic_features)
    deception, reliability = combine_scores(ling_score, aco_score, ling_feat.get("has_transcript", False))

    findings = ling_findings + aco_findings
    findings.sort(key=lambda item: item.get("weight", 0), reverse=True)

    summary = _summary(deception, reliability, findings, language)

    return {
        "linguistic_score": round(ling_score, 4),
        "acoustic_score": round(aco_score, 4),
        "deception_index": deception,
        "reliability_index": reliability,
        "risk_band": band_for(deception),
        "reliability_band": band_for(1 - deception),
        "linguistic_features": ling_feat,
        "acoustic_features": acoustic_features,
        "findings": findings,
        "summary": summary,
        "disclaimer": DISCLAIMER_ES,
        "stt_engine": stt_engine,
        "language": language,
        "method": "hybrid-lexicon-acoustic-v1",
    }


def _summary(deception: float, reliability: float, findings: list[dict], language: str) -> str:
    top = findings[:3]
    if language != "es":
        heads = "; ".join(item["title"] for item in top) or "No strong cues"
        return (
            f"Estimated reliability {reliability:.0%}. Risk band {band_for(deception)}. Cues: {heads}."
        )
    heads = "; ".join(item["title"] for item in top) or "sin pistas destacadas"
    return (
        f"Confiabilidad estimada {reliability:.0%} (riesgo {band_for(deception)}). "
        f"Principales pistas: {heads}."
    )
