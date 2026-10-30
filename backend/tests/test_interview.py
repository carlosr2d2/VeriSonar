from app.services.interview import (
    _answers_audio,
    assign_roles,
    canonicalize_short_reply,
    explode_mixed_text,
    fill_untranscribed_replies,
    format_dialogue,
    is_question,
    pair_exchanges,
    relocate_short_replies,
    snap_reply_bounds,
    speech_burst_span,
    utterances_from_words,
)
from app.services.waveform import envelope


def test_questions_and_short_answers() -> None:
    assert is_question("¿Es usted de Bogotá?")
    assert is_question("A robado alguna vez en su vida?")
    assert is_question("Está dispuesta a contestar las preguntas")
    assert not is_question("Sí")
    assert not is_question("Te juro que no")


def test_gap_groups_words_into_turns() -> None:
    words = [
        {"word": "es", "start": 0.0, "end": 0.2},
        {"word": "usted", "start": 0.21, "end": 0.5},
        {"word": "de", "start": 0.51, "end": 0.7},
        {"word": "bogotá", "start": 0.71, "end": 1.1},
        {"word": "sí", "start": 1.7, "end": 2.0},
        {"word": "ha", "start": 2.6, "end": 2.8},
        {"word": "robado", "start": 2.81, "end": 3.2},
        {"word": "alguna", "start": 3.21, "end": 3.5},
        {"word": "vez", "start": 3.51, "end": 3.8},
        {"word": "no", "start": 4.4, "end": 4.7},
    ]
    utterances = utterances_from_words(words)
    assert len(utterances) == 4
    turns = assign_roles(utterances)
    assert turns[0]["role"] == "interrogador"
    assert turns[1]["role"] == "interrogado"
    assert turns[2]["role"] == "interrogador"
    assert turns[3]["role"] == "interrogado"
    dialogue = format_dialogue(turns)
    assert "Interrogador: es usted de bogotá" in dialogue
    assert "Interrogado: sí" in dialogue
    exchanges = pair_exchanges(turns)
    assert len(exchanges) == 2
    assert exchanges[0]["answer"] == "sí"
    assert exchanges[0]["answer_start"] == 1.7
    assert exchanges[1]["answer"] == "no"


def test_answers_audio_keeps_only_subject() -> None:
    import numpy as np

    sr = 1000
    y = np.zeros(5000, dtype=np.float32)
    y[1700:2000] = 0.8
    y[4400:4700] = 0.6
    turns = [
        {"role": "interrogador", "start": 0.0, "end": 1.1},
        {"role": "interrogado", "start": 1.7, "end": 2.0},
        {"role": "interrogador", "start": 2.6, "end": 3.8},
        {"role": "interrogado", "start": 4.4, "end": 4.7},
    ]
    answers = _answers_audio(y, sr, turns)
    assert answers.size < y.size
    assert float(np.mean(np.abs(answers))) > 0.3


def test_first_person_stays_with_answer() -> None:
    utterances = [
        {"text": "se llama usted laura méndez", "start": 0.0, "end": 1.2},
        {"text": "si", "start": 1.6, "end": 1.8},
        {"text": "me llamo laura méndez", "start": 1.85, "end": 3.0},
        {"text": "nació usted en méxico", "start": 3.5, "end": 5.0},
        {"text": "sí", "start": 5.4, "end": 5.7},
    ]
    turns = assign_roles(utterances)
    assert [t["role"] for t in turns] == [
        "interrogador",
        "interrogado",
        "interrogador",
        "interrogado",
    ]
    assert "me llamo laura méndez" in turns[1]["text"]
    exchanges = pair_exchanges(turns)
    assert exchanges[0]["answer"].startswith("si")
    assert exchanges[1]["question"].startswith("nació")


def test_protocol_splits_yes_no_glued_to_next_question() -> None:
    utterances = [
        {"text": "Primera aplicación. ¿Su", "start": 0.0, "end": 2.4},
        {"text": "primer nombre es Esperanza?", "start": 2.4, "end": 7.0},
        {"text": "Sí.", "start": 7.2, "end": 7.7},
        {"text": "¿Hoy es el día domingo?", "start": 8.0, "end": 11.2},
        {"text": "No. ¿Teme usted que le haga preguntas sobre temas que no hayamos conversado?", "start": 11.5, "end": 16.8},
        {"text": "No, señora. ¿Piensa usted mentir a las preguntas que le voy a hacer?", "start": 17.0, "end": 22.0},
        {"text": "¿Habla usted italiano?", "start": 22.4, "end": 24.5},
        {"text": "No. ¿Ha viajado usted a Japón?", "start": 24.8, "end": 28.2},
        {"text": "¿Su apellido es Carrión?", "start": 28.6, "end": 31.0},
    ]
    turns = assign_roles(utterances)
    dialogue = format_dialogue(turns)
    assert "Interrogador: ¿Su primer nombre es Esperanza?" in dialogue
    assert "Interrogado: Sí." in dialogue or "Interrogado: Sí" in dialogue
    assert "Interrogado: No" in dialogue
    assert "Interrogador: ¿Teme usted" in dialogue
    assert "Interrogador: ¿Piensa usted mentir" in dialogue
    assert not any(
        turn["role"] == "interrogador" and turn["text"].lower().lstrip().startswith("no")
        for turn in turns
    )
    exchanges = pair_exchanges(turns)
    assert len(exchanges) >= 4
    assert any("Teme usted" in row["question"] and row["answer"].lower().startswith("no") for row in exchanges)
    assert any("italiano" in row["question"].lower() for row in exchanges)


def test_explode_mixed_keeps_no_senora_as_answer() -> None:
    parts = explode_mixed_text("No, señora. ¿Piensa usted mentir a las preguntas que le voy a hacer?")
    assert parts[0].lower().startswith("no")
    assert parts[1].startswith("¿Piensa")


def test_canonicalize_collapses_whisper_no_repeats() -> None:
    assert canonicalize_short_reply("No, no, no, no, no.") == "No."
    assert canonicalize_short_reply("No, señora.") == "No, señora."
    assert canonicalize_short_reply("No, señora. No.") == "No, señora."
    assert canonicalize_short_reply("Sí.") == "Sí."
    assert canonicalize_short_reply("entonces no") == "No."
    assert canonicalize_short_reply("italiano") is None
    assert canonicalize_short_reply("¿Habla usted italiano?") is None
    assert canonicalize_short_reply("Sí o No.") is None
    assert canonicalize_short_reply("Gracias.") is None


def test_fill_recovers_untranscribed_no_between_questions() -> None:
    import numpy as np

    sr = 16000
    y = np.zeros(int(6.5 * sr), dtype=np.float32)
    tone = np.arange(int(0.32 * sr))
    start = int(2.35 * sr)
    y[start : start + len(tone)] = 0.4 * np.sin(2 * np.pi * 180 * tone / sr)
    utterances = [
        {"text": "¿Habla usted italiano?", "start": 0.4, "end": 2.1},
        {"text": "¿Está usted viendo televisión en este momento?", "start": 3.6, "end": 5.8},
    ]
    filled = fill_untranscribed_replies(y, sr, utterances, transcribe_fn=lambda _clip: "No, señora.")
    turns = assign_roles(filled)
    dialogue = format_dialogue(turns)
    assert "Interrogador: ¿Habla usted italiano?" in dialogue
    assert "Interrogado: No, señora." in dialogue
    assert "Interrogador: ¿Está usted viendo televisión" in dialogue
    exchanges = pair_exchanges(turns)
    assert any("italiano" in row["question"].lower() and "no" in row["answer"].lower() for row in exchanges)


def test_speech_burst_keeps_answer_tail() -> None:
    import numpy as np

    sr = 16000
    y = np.zeros(int(3 * sr), dtype=np.float32)
    tone = np.arange(int(0.55 * sr))
    y[int(1.00 * sr) : int(1.00 * sr) + len(tone)] = 0.35 * np.sin(2 * np.pi * 180 * tone / sr)
    burst = speech_burst_span(y, sr, 0.9, 1.8)
    assert burst is not None
    assert burst[1] - burst[0] >= 0.50
    assert burst[1] > 1.45


def test_relocate_moves_answer_off_question_tail() -> None:
    import numpy as np

    sr = 16000
    y = np.zeros(int(6 * sr), dtype=np.float32)

    def put(t0: float, t1: float, freq: float = 180.0) -> None:
        i0, i1 = int(t0 * sr), int(t1 * sr)
        tone = np.arange(max(i1 - i0, 0))
        y[i0:i1] = 0.4 * np.sin(2 * np.pi * freq * tone / sr)

    put(0.20, 1.00)
    put(0.95, 1.22)
    put(2.10, 2.58)
    put(2.95, 4.80)
    turns = [
        {"role": "interrogador", "text": "¿Habla usted italiano?", "start": 0.2, "end": 1.0},
        {"role": "interrogado", "text": "No, señor.", "start": 1.00, "end": 1.36},
        {
            "role": "interrogador",
            "text": "¿Ha suministrado usted información confidencial?",
            "start": 2.90,
            "end": 4.80,
        },
    ]
    out = relocate_short_replies(y, sr, turns)
    answers = [row for row in out if row["role"] == "interrogado"]
    assert len(answers) == 1
    assert answers[0]["text"] == "No, señor."
    assert 1.9 < answers[0]["start"] < 2.3
    assert 2.5 < answers[0]["end"] < 2.8
    nxt = next(row for row in out if "suministrado" in row["text"])
    assert nxt["start"] >= answers[0]["end"] + 0.04
    exchanges = pair_exchanges(out)
    assert exchanges[0]["answer"].lower().startswith("no")
    assert exchanges[0]["answer_start"] >= 1.9
    assert exchanges[0]["end"] < nxt["start"] + 0.01


def test_snap_delays_next_question_until_answer_ends() -> None:
    import numpy as np

    sr = 16000
    y = np.zeros(int(4 * sr), dtype=np.float32)
    tone = np.arange(int(0.58 * sr))
    y[int(1.00 * sr) : int(1.00 * sr) + len(tone)] = 0.4 * np.sin(2 * np.pi * 170 * tone / sr)
    turns = [
        {"role": "interrogador", "text": "¿Habla usted italiano?", "start": 0.1, "end": 0.9},
        {"role": "interrogado", "text": "No, señora.", "start": 1.00, "end": 1.36},
        {"role": "interrogador", "text": "¿Está usted viendo televisión?", "start": 1.40, "end": 3.2},
    ]
    snapped = snap_reply_bounds(y, sr, turns)
    assert snapped[1]["end"] >= 1.50
    assert snapped[2]["start"] >= snapped[1]["end"] + 0.04
    assert snapped[2]["start"] > 1.40


def test_fill_skips_silent_gap() -> None:
    import numpy as np

    sr = 16000
    y = np.zeros(int(5 * sr), dtype=np.float32)
    utterances = [
        {"text": "¿Habla usted italiano?", "start": 0.2, "end": 1.5},
        {"text": "¿Está usted viendo televisión?", "start": 2.8, "end": 4.4},
    ]

    def boom(_clip):
        raise AssertionError("no debe transcribir un hueco en silencio")

    filled = fill_untranscribed_replies(y, sr, utterances, transcribe_fn=boom)
    assert [row["text"] for row in filled] == [row["text"] for row in utterances]


def test_envelope_normalizes_peak() -> None:
    import numpy as np

    samples = envelope(np.array([0.0, 0.5, -1.0, 0.25], dtype=np.float32), 4)
    assert max(samples) == 1.0
    assert min(samples) >= 0.0


def test_brief_answer_forms_sharp_peak() -> None:
    import numpy as np

    from app.services.waveform import CHART_WINDOW, microtremor_profile

    sr = 16000
    t = np.arange(0, 0.18, 1 / sr)
    y = (np.sin(2 * np.pi * 180 * t) * np.hanning(len(t))).astype(np.float32)
    spec = microtremor_profile(y, sr, chart_window=CHART_WINDOW)
    mags = np.array(spec["mags"])
    peak_i = int(np.argmax(mags))
    assert spec["available"]
    assert spec["kind"] == "chart"
    assert spec["duration"] == CHART_WINDOW
    assert 0.35 < peak_i / len(mags) < 0.65
    assert float(np.mean(mags[: len(mags) // 5])) < 0.15
    assert float(np.mean(mags[4 * len(mags) // 5 :])) < 0.15


def test_sustained_answer_forms_wide_mountain() -> None:
    import numpy as np

    from app.services.waveform import CHART_WINDOW, microtremor_profile

    sr = 16000
    t = np.arange(0, 1.8, 1 / sr)
    y = (np.sin(2 * np.pi * 180 * t) * (1 + 0.3 * np.sin(2 * np.pi * 10 * t))).astype(np.float32)
    spec = microtremor_profile(y, sr, chart_window=CHART_WINDOW)
    mags = np.array(spec["mags"])
    mid = mags[len(mags) // 4 : 3 * len(mags) // 4]
    assert spec["kind"] == "chart"
    assert float(np.mean(mid)) > 0.35
    assert float(np.max(mags)) == 1.0


def test_normalize_clip_bounds_keeps_answer_inside() -> None:
    from app.services.interview import normalize_clip_bounds

    start, end, answer_start, answer_end = normalize_clip_bounds(8.0, 1.0, 9.5, 0.2, 12.0)
    assert start < end
    assert start <= answer_start < answer_end <= end
    assert answer_end - answer_start >= 0.12


def test_apply_manual_clip_rewrites_wav(tmp_path, monkeypatch) -> None:
    import numpy as np
    import soundfile as sf

    from app.config import settings
    from app.services.interview import apply_manual_clip

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    sr = 16000
    y = np.zeros(sr * 4, dtype=np.float32)
    y[int(0.4 * sr) : int(1.2 * sr)] = 0.4
    y[int(2.0 * sr) : int(2.4 * sr)] = 0.5
    wav = tmp_path / "src.wav"
    sf.write(str(wav), y, sr)
    interview = {
        "exchanges": [
            {
                "index": 1,
                "question": "¿Su primer nombre es Esperanza?",
                "answer": "Sí.",
                "start": 0.4,
                "end": 1.0,
                "answer_start": 0.8,
                "answer_end": 1.0,
                "samples": [0.1],
            }
        ]
    }
    out = apply_manual_clip(
        wav,
        "audio1",
        interview,
        1,
        0.3,
        2.5,
        1.95,
        2.45,
        language="es",
        enable_praat=False,
    )
    row = out["exchanges"][0]
    assert row["start"] == 0.3
    assert row["answer_start"] == 1.95
    assert row["end"] == 2.5
    assert (tmp_path / "audio1" / "clips" / "01.wav").exists()
    assert row["samples"]


def test_apply_clip_text_updates_question_and_kind() -> None:
    from app.services.interview import apply_clip_text

    interview = {
        "turns": [
            {"role": "interrogador", "text": "¿Ha viajado usted a Japón?", "start": 1.0, "end": 2.4},
            {"role": "interrogado", "text": "No, señora.", "start": 2.5, "end": 3.0},
        ],
        "exchanges": [
            {
                "index": 12,
                "question": "¿Ha viajado usted a Japón?",
                "answer": "No, señora.",
                "start": 1.0,
                "end": 3.0,
                "answer_start": 2.5,
                "answer_end": 3.0,
                "kind": "control",
                "kind_label": "Control",
                "fm_stress": 0.4,
                "acoustic_score": 0.3,
                "vsa_score": 0.35,
            }
        ],
        "vsa": {
            "items": [
                {
                    "index": 12,
                    "question": "¿Ha viajado usted a Japón?",
                    "answer": "No, señora.",
                    "kind": "control",
                    "kind_label": "Control",
                    "fm_stress": 0.4,
                    "acoustic_score": 0.3,
                    "vsa_score": 0.35,
                }
            ]
        },
    }
    out = apply_clip_text(interview, 12, "¿Ha viajado usted a Japón?", "No.", language="es")
    row = out["exchanges"][0]
    assert row["answer"] == "No."
    assert row["question"] == "¿Ha viajado usted a Japón?"
    assert out["turns"][1]["text"] == "No."
    assert out["vsa"]["items"][0]["answer"] == "No."


def test_apply_clip_chart_inclusion_toggles_report_flags() -> None:
    from app.services.interview import apply_clip_chart_inclusion

    interview = {
        "exchanges": [
            {"index": 11, "include_vsa_in_report": True, "include_comb_in_report": True},
        ]
    }
    out = apply_clip_chart_inclusion(interview, 11, include_comb=False)
    row = out["exchanges"][0]
    assert row["include_comb_in_report"] is False
    assert row["include_vsa_in_report"] is True
    out = apply_clip_chart_inclusion(interview, 11, include_vsa=False)
    assert out["exchanges"][0]["include_vsa_in_report"] is False
    out = apply_clip_chart_inclusion(interview, 11, vsa_note="  Pico irregular en la respuesta  ")
    assert out["exchanges"][0]["vsa_report_note"] == "Pico irregular en la respuesta"


def test_comb_profile_keeps_pitch_cycles_without_padding() -> None:
    import numpy as np

    from app.services.waveform import CHART_WINDOW, comb_profile

    sr = 16000
    f0 = 180.0
    seconds = 0.40
    t = np.arange(0, seconds, 1 / sr)
    y = (np.sin(2 * np.pi * f0 * t) * np.hanning(len(t))).astype(np.float32)
    spec = comb_profile(y, sr)
    samples = np.array(spec["samples"])
    peaks = int(np.sum((samples[1:-1] > samples[:-2]) & (samples[1:-1] > samples[2:])))
    assert spec["available"]
    assert spec["kind"] == "comb"
    assert spec["duration"] == round(seconds, 3)
    assert spec["duration"] < CHART_WINDOW
    assert float(np.min(samples)) >= -0.001
    assert float(np.max(samples)) > 0.8
    assert 40 < peaks < 140
