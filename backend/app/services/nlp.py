from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.lexicons.es_latam import (
    COGNITIVE_LOAD_ES,
    DISTANCING,
    FILLERS_EN,
    FILLERS_ES,
    FIRST_PERSON,
    HEDGES_EN,
    HEDGES_ES,
    NEGATIONS_ES,
    PROTESTATIONS_EN,
    PROTESTATIONS_ES,
)

logger = get_logger(__name__)

TOKEN_RE = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]


def ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _count_phrases(text: str, phrases: set[str]) -> int:
    blob = f" {text.lower()} "
    return sum(blob.count(f" {phrase} ") for phrase in phrases)


def linguistic_features(text: str, language: str = "es") -> dict:
    tokens = tokenize(text)
    n = max(len(tokens), 1)
    sentences = [s for s in re.split(r"[.!?¿¡]+", text or "") if s.strip()]
    avg_len = (sum(len(tokenize(s)) for s in sentences) / len(sentences)) if sentences else 0.0
    types = len(set(tokens))
    ttr = types / n

    hedges = HEDGES_ES | (HEDGES_EN if language == "en" else set())
    fillers = FILLERS_ES | (FILLERS_EN if language == "en" else set())
    protests = PROTESTATIONS_ES | (PROTESTATIONS_EN if language == "en" else set())

    hedge_hits = _count_phrases(text, hedges) + sum(1 for t in tokens if t in hedges)
    filler_hits = _count_phrases(text, fillers)
    protest_hits = _count_phrases(text, protests)
    negation_hits = sum(1 for t in tokens if t in NEGATIONS_ES)
    first_person = sum(1 for t in tokens if t in FIRST_PERSON)
    distancing = sum(1 for t in tokens if t in DISTANCING)
    cognitive = _count_phrases(text, COGNITIVE_LOAD_ES)

    repeats = sum(1 for _, c in Counter(ngrams(tokens, 3)).items() if c > 1)

    return {
        "token_count": n if text else 0,
        "sentence_count": len(sentences),
        "avg_sentence_len": round(avg_len, 2),
        "type_token_ratio": round(ttr, 4),
        "hedge_rate": round(hedge_hits / n, 4),
        "filler_rate": round(filler_hits / n, 4),
        "negation_rate": round(negation_hits / n, 4),
        "first_person_rate": round(first_person / n, 4),
        "distancing_rate": round(distancing / n, 4),
        "protestation_rate": round(protest_hits / n, 4),
        "cognitive_rate": round(cognitive / n, 4),
        "repeat_trigrams": repeats,
        "has_transcript": bool(text and text.strip()),
    }


def linguistic_risk_score(features: dict) -> tuple[float, list[dict]]:
    findings: list[dict] = []
    if not features.get("has_transcript"):
        return 0.4, [
            {
                "code": "LING_NO_TRANSCRIPT",
                "category": "linguistico",
                "severity": "info",
                "title": "Sin transcripción",
                "detail": (
                    "No hay modelo STT local disponible o el audio no produjo texto. "
                    "El índice lingüístico queda en neutro. Coloque un modelo Vosk o Whisper en /data/models."
                ),
                "evidence": None,
                "weight": 0.0,
            }
        ]

    score = 0.18
    mapping = [
        (
            "hedge_rate",
            0.04,
            0.22,
            "LING_HEDGES",
            "Hedging / atenuación",
            "Expresiones de duda (creo, tal vez, como que) aumentan la distancia epistémica del relato.",
        ),
        (
            "filler_rate",
            0.03,
            0.16,
            "LING_FILLERS",
            "Muletillas regionales",
            "Muletillas frecuentes (este, o sea, pues, tipo, po) pueden señalar planificación en línea.",
        ),
        (
            "negation_rate",
            0.05,
            0.12,
            "LING_NEGATION",
            "Negaciones densas",
            "Una tasa alta de negación aparece en relatos defensivos. Evaluar el contexto.",
        ),
        (
            "protestation_rate",
            0.01,
            0.14,
            "LING_PROTEST",
            "Protestas de sinceridad",
            "Fórmulas como «te juro» o «la verdad es» a veces compensan falta de evidencia.",
        ),
        (
            "cognitive_rate",
            0.01,
            0.1,
            "LING_COGLOAD",
            "Carga cognitiva verbal",
            "Marcadores de reformulación y olvido («cómo te explico», «no recuerdo»).",
        ),
        (
            "distancing_rate",
            0.04,
            0.1,
            "LING_DISTANCE",
            "Distanciamiento pronominal",
            "Menos yo/nosotros y más uno/ellos puede reducir la apropiación del evento.",
        ),
    ]

    for key, threshold, weight, code, title, detail in mapping:
        value = features.get(key) or 0
        if value >= threshold:
            w = min(weight, value * 2)
            score += w
            findings.append(
                {
                    "code": code,
                    "category": "linguistico",
                    "severity": "media" if value < threshold * 2 else "alta",
                    "title": title,
                    "detail": detail,
                    "evidence": f"{key}={value:.2%}",
                    "weight": round(w, 4),
                }
            )

    fp = features.get("first_person_rate") or 0
    if features.get("token_count", 0) > 40 and fp < 0.03:
        w = 0.12
        score += w
        findings.append(
            {
                "code": "LING_NO_I",
                "category": "linguistico",
                "severity": "media",
                "title": "Baja primera persona",
                "detail": "Relatos verosímiles en español suelen anclarse en yo/nosotros. La omisión puede ser estilo o evasión.",
                "evidence": f"primera persona {fp:.2%}",
                "weight": w,
            }
        )

    if (features.get("repeat_trigrams") or 0) >= 3:
        w = 0.08
        score += w
        findings.append(
            {
                "code": "LING_REPEAT",
                "category": "linguistico",
                "severity": "baja",
                "title": "Repeticiones",
                "detail": "Trigramas repetidos pueden indicar ensayo o bloqueo léxico.",
                "evidence": f"{features['repeat_trigrams']} trigramas repetidos",
                "weight": w,
            }
        )

    transformer_boost = _optional_transformer_score(features)
    if transformer_boost is not None:
        score = 0.65 * score + 0.35 * transformer_boost[0]
        findings.extend(transformer_boost[1])

    return float(min(1.0, max(0.0, score))), findings


def _optional_transformer_score(features: dict) -> tuple[float, list[dict]] | None:
    if not settings.enable_transformers:
        return None
    model_path = Path(settings.nlp_model_path)
    if not model_path.exists():
        logger.info("transformer_model_absent", path=str(model_path))
        return None
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(str(model_path), local_files_only=True)
        clf = pipeline("text-classification", model=model, tokenizer=tokenizer)
        # El texto original no viaja en features; esta rama se reserva para uso futuro
        # con el transcript inyectado por el orquestador.
        _ = clf
        return None
    except Exception as exc:
        logger.warning("transformer_offline_failed", error=str(exc))
        return None
