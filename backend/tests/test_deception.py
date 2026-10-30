from app.services.acoustic import acoustic_risk_score
from app.services.deception import analyze_signals, band_for, combine_scores
from app.services.nlp import linguistic_features, linguistic_risk_score
from app.services.praat_acoustic import merge_acoustic_features


def test_spanish_hedges_raise_score() -> None:
    text = (
        "Este, la verdad es que yo creo que tal vez no estuve ahí, "
        "o sea, no recuerdo bien, te juro que no fue así, pues como que no sé."
    )
    features = linguistic_features(text, "es")
    score, findings = linguistic_risk_score(features)
    codes = {item["code"] for item in findings}
    assert features["has_transcript"]
    assert score > 0.3
    assert "LING_HEDGES" in codes or "LING_FILLERS" in codes or "LING_PROTEST" in codes


def test_clean_narrative_is_lower_risk() -> None:
    text = (
        "Llegué a la oficina a las ocho. Revisé el expediente con el equipo. "
        "Firmamos el acta y salimos a las doce. Eso es lo que ocurrió."
    )
    risky = linguistic_features(
        "Este, te juro que tal vez no, o sea, no sé, creo que capaz no fue así.",
        "es",
    )
    clean = linguistic_features(text, "es")
    risky_score, _ = linguistic_risk_score(risky)
    clean_score, _ = linguistic_risk_score(clean)
    assert clean_score < risky_score


def test_combine_scores_bounds() -> None:
    d, r = combine_scores(0.8, 0.7, True)
    assert 0 < d < 1
    assert abs((d + r) - 1) < 1e-6
    assert band_for(0.2) == "bajo"
    assert band_for(0.8) == "crítico"


def test_praat_jitter_and_hnr_findings() -> None:
    score, findings = acoustic_risk_score(
        {
            "available": True,
            "praat": True,
            "pause_ratio": 0.1,
            "pitch_std_hz": 10,
            "jitter_local": 0.022,
            "shimmer_local": 0.08,
            "hnr_mean_db": 7.5,
            "speech_rate_onsets": 3.0,
            "energy_std": 0.01,
            "intensity_std_db": 9.2,
        }
    )
    codes = {item["code"] for item in findings}
    assert score > 0.2
    assert "ACO_JITTER" in codes
    assert "ACO_HNR" in codes
    assert "ACO_SHIMMER" in codes


def test_merge_prefers_praat_jitter() -> None:
    merged = merge_acoustic_features(
        {"available": True, "jitter_approx": 0.2, "pitch_mean_hz": 100},
        {"available": True, "jitter_local": 0.01, "pitch_mean_hz": 180, "praat": True},
    )
    assert merged["praat"] is True
    assert merged["jitter_local"] == 0.01
    assert merged["jitter_approx"] == 0.01
    assert merged["pitch_mean_hz"] == 180
    assert merged["acoustic_engine"] == "praat+librosa"


def test_merge_without_praat_keeps_librosa() -> None:
    merged = merge_acoustic_features({"available": True, "jitter_approx": 0.04}, {"available": False})
    assert merged["praat"] is False
    assert merged["acoustic_engine"] == "librosa"
    assert merged["jitter_approx"] == 0.04


def test_pipeline_without_audio_features() -> None:
    result = analyze_signals(
        "Te juro que no fue así, o sea, creo que tal vez me confundí.",
        "es",
        {"available": False},
        "none",
    )
    assert "disclaimer" in result
    assert result["deception_index"] >= 0
    assert result["findings"]
