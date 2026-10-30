import numpy as np

from app.services.vsa import (
    apply_baseline,
    classify_question_kind,
    micro_oscillation_features,
    score_answer_clip,
)


def test_classify_guion_questions() -> None:
    assert classify_question_kind("¿Se llama usted Laura Méndez?") == "control"
    assert classify_question_kind("¿Nació usted en México?") == "control"
    assert classify_question_kind("¿Está usted ahora sentada en esta sala?") == "control"
    assert classify_question_kind("¿Trabaja usted en el almacén desde el año pasado?") == "control"
    assert classify_question_kind("¿Sabe usted que faltan cajas del inventario?") == "stimulus"
    assert classify_question_kind("¿Tomó usted mercancía del almacén sin registrarla?") == "relevant"
    assert classify_question_kind("¿Vio usted a alguien sacar cajas sin firmar la bitácora?") == "relevant"
    assert classify_question_kind("¿Ha mentido alguna vez para evitar un problema en el trabajo?") == "relevant"
    assert classify_question_kind("¿Quiere agregar algo?") == "control"


def test_baseline_flags_relevant_above_controls() -> None:
    items = [
        {"index": 1, "kind": "control", "kind_label": "Control", "vsa_score": 0.30},
        {"index": 2, "kind": "control", "kind_label": "Control", "vsa_score": 0.32},
        {"index": 3, "kind": "stimulus", "kind_label": "Estímulo", "vsa_score": 0.33},
        {"index": 4, "kind": "relevant", "kind_label": "Relevante", "vsa_score": 0.55},
    ]
    out = apply_baseline(items)
    assert abs(out["baseline"] - 0.31) < 1e-6
    assert out["items"][2]["flagged"] is False
    assert out["items"][3]["flagged"] is True
    assert out["flagged_count"] == 1
    assert out["vsa_index"] == 0.55


def test_control_near_baseline_is_not_flagged() -> None:
    items = [
        {"index": 1, "kind": "control", "vsa_score": 0.40},
        {"index": 2, "kind": "relevant", "vsa_score": 0.42},
    ]
    out = apply_baseline(items)
    assert out["items"][1]["flagged"] is False


def test_am_carrier_has_8_12_hz_energy() -> None:
    sr = 16000
    t = np.arange(0, 2.0, 1 / sr)
    carrier = np.sin(2 * np.pi * 180 * t)
    modulated = carrier * (1 + 0.5 * np.sin(2 * np.pi * 10 * t))
    with_mod = micro_oscillation_features(modulated.astype(np.float32), sr)
    plain = micro_oscillation_features(carrier.astype(np.float32), sr)
    assert with_mod["fm_8_12_ratio"] > plain["fm_8_12_ratio"]
    assert with_mod["fm_stress"] < plain["fm_stress"]


def test_score_clip_returns_kind_and_score() -> None:
    sr = 16000
    y = (0.1 * np.sin(2 * np.pi * 180 * np.arange(0, 0.8, 1 / sr))).astype(np.float32)
    row = score_answer_clip(y, sr, "¿Se llama usted Laura Méndez?", "Sí. Me llamo Laura Méndez.")
    assert row["kind"] == "control"
    assert 0.0 <= row["vsa_score"] <= 1.0
