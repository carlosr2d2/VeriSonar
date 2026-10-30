from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import soundfile as sf

from app.config import settings
from app.core.logging import get_logger
from app.services.stt import TranscriptionResult, transcribe_clip
from app.services.waveform import (
    CHART_WINDOW,
    comb_profile,
    envelope,
    extract_clip,
    microtremor_profile,
    render_comb_png,
    render_vsa_png,
    render_waveform_png,
)

logger = get_logger(__name__)

GAP_SECONDS = 0.28
ENVELOPE_BINS = 1400
CLIP_ENVELOPE_BINS = 640
REPLY_GAP_MIN = 0.35
REPLY_GAP_MAX = 3.2
REPLY_TAIL_SKIP = 0.12
REPLY_MIN_VOICED = 0.08
REPLY_MIN_RATIO = 0.08
ANSWER_LAG = 0.32
ANSWER_MIN_DUR = 0.16
ANSWER_MAX_DUR = 0.90
PROTOCOL_REPLY_PROMPT = "El evaluado responde: Sí. No. No, señora."
SHORT_PARTICLE = re.compile(
    r"\b(sí|si|no)\b(?:\s*,?\s*(señora|señor|señorita))?",
    re.IGNORECASE,
)

QUESTION_START = re.compile(
    r"^(¿|qué\b|que\b|quién\b|quien\b|dónde\b|donde\b|cuándo\b|cuando\b|cómo\b|como\b|"
    r"por qué\b|por que\b|cuál\b|cual\b|cuánto\b|cuanto\b|"
    r"es usted|está usted|esta usted|se llama|nació|nacio|sabe usted|tomó usted|tomo usted|"
    r"vio usted|ha mentido|a mentido|ha robado|a robado|robó|robo usted|toma usted|quiere agregar|"
    r"está dispuesta|esta dispuesta|esta es una entrevista|responda con|"
    r"are you|did you|have you|were you|do you)",
    re.IGNORECASE,
)
SHORT_ANSWER = re.compile(
    r"^(sí|si|no|claro|bueno|ok|okay|vale|ajá|aja|mm+|uh+|este|listo|perfecto)"
    r"(\s+(señora|señor|señorita))?"
    r"(\s+\w+){0,2}$",
    re.IGNORECASE,
)
ANSWER_START = re.compile(
    r"^(me llamo|me lo|yo |entro |entré|entró|salgo|llegué|ese día|una vez|nada más|"
    r"eso es|te juro|o sea|la verdad|no recuerdo|digamos|pues )",
    re.IGNORECASE,
)
QUESTION_SPAN = re.compile(r"¿[^¿]+?(?:\?|(?=¿)|$)")


def media_dir(audio_id: str) -> Path:
    path = Path(settings.upload_dir) / audio_id
    (path / "clips").mkdir(parents=True, exist_ok=True)
    return path


def question_score(text: str) -> int:
    raw = (text or "").strip()
    if not raw:
        return 0
    score = 0
    lowered = raw.lower()
    if "¿" in raw or raw.endswith("?"):
        score += 3
    if QUESTION_START.search(lowered):
        score += 3
    head = lowered.replace("¿", " ").split()
    if "usted" in head[:10]:
        score += 2
    if SHORT_ANSWER.match(re.sub(r"[^\wáéíóúñü¿? ]+", " ", lowered).strip()):
        score -= 3
    if ANSWER_START.search(lowered):
        score -= 3
    if lowered.startswith(("te juro", "o sea", "la verdad", "no recuerdo", "no sé", "no se")):
        score -= 2
    return score


def is_question(text: str) -> bool:
    return question_score(text) >= 2


def _plain(text: str) -> str:
    return re.sub(r"[^\wáéíóúñü ]+", " ", (text or "").lower()).strip()


def looks_like_short_reply(text: str) -> bool:
    return bool(SHORT_ANSWER.match(_plain(text)))


def canonicalize_short_reply(text: str) -> str | None:
    """Deja un sí/no usable y descarta el 'No, no, no...' que Whisper alucina en recortes."""
    raw = (text or "").strip()
    if not raw:
        return None
    stripped = QUESTION_SPAN.sub(" ", raw)
    stripped = re.sub(r"[¿?]", " ", stripped)
    stripped = re.sub(r"\b(sí|si)\s+o\s+no\b", " ", stripped, flags=re.IGNORECASE)
    matches = list(SHORT_PARTICLE.finditer(stripped))
    if not matches:
        return None
    tokens = _plain(stripped).split()
    leftover = [tok for tok in tokens if tok not in {"sí", "si", "no", "señora", "señor", "señorita"}]
    chosen = matches[-1] if leftover else matches[0]
    title = chosen.group(2)
    particle = chosen.group(1)
    if not title:
        for match in matches[:2]:
            if match.group(2):
                particle = match.group(1)
                title = match.group(2)
                break
    head = "Sí" if particle.lower() in {"sí", "si"} else "No"
    if title:
        return f"{head}, {title.lower()}."
    return f"{head}."


def _frame_rms(y: np.ndarray, sr: int, start: float, end: float, frame_ms: float = 20.0) -> np.ndarray:
    i0 = max(0, int(start * sr))
    i1 = min(len(y), int(end * sr))
    clip = y[i0:i1]
    if clip.size == 0:
        return np.array([], dtype=np.float32)
    frame = max(1, int(sr * frame_ms / 1000.0))
    count = int(np.ceil(clip.size / frame))
    rms = np.zeros(count, dtype=np.float32)
    for index in range(count):
        piece = clip[index * frame : (index + 1) * frame]
        rms[index] = float(np.sqrt(np.mean(np.square(piece.astype(np.float32)))))
    return rms


def _gap_speech_stats(y: np.ndarray, sr: int, start: float, end: float) -> dict:
    rms = _frame_rms(y, sr, start, end)
    if rms.size == 0:
        return {"voiced": 0.0, "ratio": 0.0}
    noise = float(np.median(rms)) + 1e-8
    voiced = rms > max(noise * 3.5, 0.012)
    return {
        "voiced": float(np.sum(voiced) * 0.02),
        "ratio": float(np.mean(voiced)),
    }


def _loudest_span(y: np.ndarray, sr: int, start: float, end: float, width: float = 0.36) -> tuple[float, float]:
    i0 = max(0, int(start * sr))
    i1 = min(len(y), int(end * sr))
    clip = y[i0:i1]
    win = max(1, int(width * sr))
    if clip.size <= win:
        return float(start), float(end)
    hop = max(1, int(0.01 * sr))
    best_e = -1.0
    best_i = 0
    for index in range(0, clip.size - win + 1, hop):
        energy = float(np.mean(np.square(clip[index : index + win])))
        if energy > best_e:
            best_e = energy
            best_i = index
    t0 = start + best_i / sr
    t1 = min(end, t0 + width)
    return float(t0), float(t1)


def _close_holes(voiced: np.ndarray, max_gap: int = 3) -> np.ndarray:
    filled = voiced.copy()
    last = -999
    for index, flag in enumerate(voiced):
        if flag:
            if 0 < index - last - 1 <= max_gap:
                filled[last + 1 : index] = True
            last = index
    return filled


def list_speech_bursts(y: np.ndarray, sr: int, start: float, end: float, min_dur: float = 0.10) -> list[tuple[float, float]]:
    rms = _frame_rms(y, sr, start, end)
    if rms.size == 0:
        return []
    noise = min(float(np.percentile(rms, 20)), 0.018) + 1e-8
    voiced = _close_holes(rms > max(noise * 3.0, 0.012), 4)
    rows: list[tuple[float, float]] = []
    cursor = 0
    while cursor < voiced.size:
        if not voiced[cursor]:
            cursor += 1
            continue
        stop = cursor
        while stop < voiced.size and voiced[stop]:
            stop += 1
        t0 = start + cursor * 0.02
        t1 = start + stop * 0.02
        if t1 - t0 >= min_dur:
            rows.append((float(t0), float(t1)))
        cursor = stop
    return rows


def speech_burst_span(
    y: np.ndarray,
    sr: int,
    start: float,
    end: float,
    pad_before: float = 0.04,
    pad_after: float = 0.10,
) -> tuple[float, float] | None:
    """Devuelve el tramo de voz más largo, con un poco de cola para no cortar la sílaba."""
    bursts = list_speech_bursts(y, sr, start, end, min_dur=0.06)
    if not bursts:
        return None
    t0, t1 = max(bursts, key=lambda item: item[1] - item[0])
    t0 = max(start, t0 - pad_before)
    t1 = min(end, t1 + pad_after)
    if t1 - t0 < 0.16:
        t1 = min(end, t0 + 0.22)
    return float(t0), float(t1)


def _reply_text_between(turns: list[dict], start_i: int, end_i: int) -> str | None:
    for turn in turns[start_i:end_i]:
        if turn.get("role") == "interrogado" and looks_like_short_reply(turn.get("text") or ""):
            return str(turn["text"]).strip()
    return None


def relocate_short_replies(
    y: np.ndarray,
    sr: int,
    turns: list[dict],
    transcribe_fn=None,
) -> list[dict]:
    """Mueve el sí/no al burst real (~1 s tras la pregunta), no a la última sílaba de la pregunta."""
    if not turns or y is None or sr <= 0:
        return turns
    duration = float(len(y) / sr)
    questions = [
        index
        for index, turn in enumerate(turns)
        if turn.get("role") == "interrogador" and question_score(turn.get("text") or "") >= 2
    ]
    if not questions:
        return turns
    placed: dict[int, dict] = {}
    for n, qi in enumerate(questions):
        q = turns[qi]
        nxt_i = questions[n + 1] if n + 1 < len(questions) else len(turns)
        q_end = float(q["end"])
        look1 = min(duration, float(turns[nxt_i]["start"]) + 1.4 if nxt_i < len(turns) else q_end + 2.4)
        answer = None
        for b0, b1 in list_speech_bursts(y, sr, q_end - 0.04, look1):
            dur = b1 - b0
            if b0 >= q_end + ANSWER_LAG and ANSWER_MIN_DUR <= dur <= ANSWER_MAX_DUR:
                answer = (b0, min(b1 + 0.08, look1))
                break
        if not answer:
            continue
        text = _reply_text_between(turns, qi + 1, nxt_i)
        if not text and transcribe_fn is not None:
            i0 = max(0, int(answer[0] * sr))
            i1 = min(len(y), int(answer[1] * sr))
            text = canonicalize_short_reply(transcribe_fn(y[i0:i1]) or "")
        if not text:
            continue
        placed[qi] = {
            "role": "interrogado",
            "text": text,
            "start": round(answer[0], 3),
            "end": round(answer[1], 3),
        }
        logger.info("relocated_short_reply", question=str(q.get("text") or "")[:48], start=answer[0], end=answer[1], text=text)
    if not placed:
        return turns
    rebuilt: list[dict] = []
    skip_until = -1
    for index, turn in enumerate(turns):
        if index < skip_until:
            continue
        if index in placed:
            question = dict(turn)
            reply = placed[index]
            question["end"] = round(min(float(question["end"]), float(reply["start"]) - 0.04), 3)
            if float(question["end"]) <= float(question["start"]):
                question["end"] = round(float(question["start"]) + 0.12, 3)
            rebuilt.append(question)
            rebuilt.append(reply)
            nxt_q = next((qi for qi in questions if qi > index), None)
            skip_until = nxt_q if nxt_q is not None else len(turns)
            if nxt_q is not None:
                nxt = dict(turns[nxt_q])
                nxt["start"] = round(max(float(nxt["start"]), float(reply["end"]) + 0.05), 3)
                if float(nxt["end"]) <= float(nxt["start"]):
                    nxt["end"] = round(float(nxt["start"]) + 0.3, 3)
                turns[nxt_q] = nxt
            continue
        if turn.get("role") == "interrogado" and looks_like_short_reply(turn.get("text") or ""):
            continue
        rebuilt.append(dict(turn))
    return rebuilt


def snap_reply_bounds(y: np.ndarray, sr: int, turns: list[dict]) -> list[dict]:
    """Estira la respuesta hasta el final de la voz y retrasa la pregunta siguiente."""
    out = [dict(turn) for turn in turns]
    duration = float(len(y) / sr) if sr else 0.0
    for index, turn in enumerate(out):
        if turn.get("role") != "interrogado":
            continue
        nxt = out[index + 1] if index + 1 < len(out) else None
        look0 = max(0.0, float(turn["start"]) - 0.08)
        look1 = min(duration, float(turn["end"]) + 0.55)
        if nxt:
            look1 = min(look1, float(nxt["start"]) + 0.12)
        burst = speech_burst_span(y, sr, look0, look1)
        if burst:
            turn["start"] = round(burst[0], 3)
            turn["end"] = round(max(burst[1], burst[0] + 0.16), 3)
        else:
            turn["end"] = round(min(look1, float(turn["end"]) + 0.10), 3)
        if nxt and nxt.get("role") == "interrogador":
            delayed = max(float(nxt["start"]), float(turn["end"]) + 0.05)
            nxt["start"] = round(delayed, 3)
            if float(nxt["end"]) <= delayed:
                nxt["end"] = round(delayed + max(0.20, float(nxt["end"]) - float(nxt["start"])), 3)
    return out


def _recover_gap_reply(
    y: np.ndarray,
    sr: int,
    gap0: float,
    gap1: float,
    transcribe_fn,
    retry_fn=None,
) -> dict | None:
    listen0 = gap0 + REPLY_TAIL_SKIP
    listen1 = gap1 - 0.08
    if listen1 - listen0 < 0.28:
        listen0 = gap0 + 0.08
        listen1 = gap1
    if listen1 - listen0 < 0.20:
        return None
    stats = _gap_speech_stats(y, sr, listen0, listen1)
    if stats["voiced"] < REPLY_MIN_VOICED or stats["ratio"] < REPLY_MIN_RATIO:
        return None
    i0 = max(0, int(listen0 * sr))
    i1 = min(len(y), int(listen1 * sr))
    clip = y[i0:i1]
    raw = (transcribe_fn(clip) or "").strip()
    text = canonicalize_short_reply(raw)
    if not text and retry_fn is not None:
        raw = (retry_fn(clip) or "").strip()
        text = canonicalize_short_reply(raw)
    if not text:
        logger.info(
            "short_reply_not_recovered",
            start=round(listen0, 3),
            end=round(gap1, 3),
            voiced=round(stats["voiced"], 3),
            ratio=round(stats["ratio"], 3),
            raw=raw[:80],
        )
        return None
    burst = speech_burst_span(y, sr, listen0, listen1)
    if burst:
        t0, t1 = burst
    else:
        t0, t1 = _loudest_span(y, sr, listen0, listen1)
    logger.info("recovered_short_reply", start=round(t0, 3), end=round(t1, 3), text=text, raw=raw[:80])
    return {"text": text, "start": round(t0, 3), "end": round(max(t1, t0 + 0.16), 3)}


def fill_untranscribed_replies(
    y: np.ndarray,
    sr: int,
    utterances: list[dict],
    transcribe_fn=None,
) -> list[dict]:
    """Si hay voz entre dos preguntas y Whisper no escribió el sí/no, transcribe solo ese hueco."""
    prepared = merge_question_fragments(explode_utterances(list(utterances)))
    if not prepared or y is None or sr <= 0:
        return prepared
    decoder = transcribe_fn or transcribe_clip
    retry_fn = (
        (lambda clip: transcribe_clip(clip, initial_prompt=PROTOCOL_REPLY_PROMPT))
        if transcribe_fn is None
        else None
    )
    duration = float(len(y) / sr)
    extras: list[dict] = []
    for index, item in enumerate(prepared):
        if question_score(item["text"]) < 2:
            continue
        nxt = prepared[index + 1] if index + 1 < len(prepared) else None
        if nxt and (looks_like_short_reply(nxt["text"]) or question_score(nxt["text"]) < 2):
            continue
        gap0 = float(item["end"])
        gap1 = float(nxt["start"]) if nxt else duration
        span = gap1 - gap0
        if span < REPLY_GAP_MIN or span > REPLY_GAP_MAX:
            continue
        reply = _recover_gap_reply(y, sr, gap0, gap1, decoder, retry_fn=retry_fn)
        if reply:
            extras.append(reply)
    if not extras:
        return prepared
    combined = prepared + extras
    combined.sort(key=lambda row: (float(row["start"]), float(row["end"])))
    return combined


def explode_mixed_text(text: str) -> list[str]:
    """Separa 'No. ¿Pregunta?' en respuesta + pregunta. Whisper suele pegarlas."""
    raw = (text or "").strip()
    if not raw:
        return []
    if "¿" not in raw:
        return [raw]
    parts: list[str] = []
    cursor = 0
    for match in QUESTION_SPAN.finditer(raw):
        before = raw[cursor : match.start()].strip(" \t,.;:-")
        if before:
            parts.append(before)
        question = match.group().strip()
        if question:
            parts.append(question)
        cursor = match.end()
    tail = raw[cursor:].strip(" \t,.;:-")
    if tail:
        parts.append(tail)
    return parts or [raw]


def _split_times(start: float, end: float, pieces: list[str]) -> list[dict]:
    span = max(float(end) - float(start), 0.05)
    weights = [max(len(piece), 1) for piece in pieces]
    total = float(sum(weights))
    cursor = float(start)
    rows: list[dict] = []
    for index, piece in enumerate(pieces):
        duration = span * (weights[index] / total)
        piece_end = float(end) if index == len(pieces) - 1 else cursor + duration
        rows.append({"text": piece, "start": round(cursor, 3), "end": round(float(piece_end), 3)})
        cursor = float(piece_end)
    return rows


def explode_utterances(utterances: list[dict]) -> list[dict]:
    exploded: list[dict] = []
    for item in utterances:
        pieces = explode_mixed_text(str(item.get("text") or ""))
        if len(pieces) <= 1:
            exploded.append(item)
            continue
        exploded.extend(_split_times(float(item["start"]), float(item["end"]), pieces))
    return exploded


def merge_question_fragments(utterances: list[dict]) -> list[dict]:
    """Une '¿Su' + 'primer nombre es Esperanza?' partidos por el STT."""
    merged: list[dict] = []
    for item in utterances:
        if not merged:
            merged.append(dict(item))
            continue
        prev = merged[-1]
        prev_text = str(prev.get("text") or "").strip()
        text = str(item.get("text") or "").strip()
        open_question = ("¿" in prev_text or question_score(prev_text) >= 2) and not prev_text.endswith("?")
        continuation = (
            bool(text)
            and not looks_like_short_reply(text)
            and not text.startswith("¿")
            and not looks_like_short_reply(prev_text)
        )
        if open_question and continuation:
            prev["text"] = f"{prev_text} {text}".strip()
            prev["end"] = item["end"]
        else:
            merged.append(dict(item))
    return merged


def _group_text(group: list[dict]) -> str:
    return " ".join(str(word.get("word") or "") for word in group).strip()


def _starts_question_token(word: str) -> bool:
    token = (word or "").strip()
    return token.startswith("¿") or token == "¿"


def utterances_from_words(words: list[dict], gap: float = GAP_SECONDS) -> list[dict]:
    if not words:
        return []
    groups: list[list[dict]] = [[words[0]]]
    for item in words[1:]:
        previous = groups[-1][-1]
        prev_text = _group_text(groups[-1])
        token = str(item.get("word") or "")
        gap_hit = float(item.get("start") or 0) - float(previous.get("end") or 0) >= gap
        reply_then_question = _starts_question_token(token) and looks_like_short_reply(prev_text)
        question_then_reply = prev_text.rstrip().endswith("?") and looks_like_short_reply(token)
        if gap_hit or reply_then_question or question_then_reply:
            groups.append([item])
        else:
            groups[-1].append(item)
    utterances: list[dict] = []
    for group in groups:
        text = _group_text(group)
        if not text:
            continue
        utterances.append(
            {
                "text": text,
                "start": float(group[0].get("start") or 0),
                "end": float(group[-1].get("end") or group[0].get("start") or 0),
            }
        )
    return explode_utterances(utterances)


def merge_same_role(turns: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            incoming_question = turn["role"] == "interrogador" and question_score(turn["text"]) >= 2
            if incoming_question:
                merged.append(
                    {
                        "role": turn["role"],
                        "text": turn["text"],
                        "start": turn["start"],
                        "end": turn["end"],
                    }
                )
                continue
            merged[-1]["text"] = f"{merged[-1]['text']} {turn['text']}".strip()
            merged[-1]["end"] = turn["end"]
        else:
            merged.append(
                {
                    "role": turn["role"],
                    "text": turn["text"],
                    "start": turn["start"],
                    "end": turn["end"],
                }
            )
    return merged


def assign_roles(utterances: list[dict]) -> list[dict]:
    prepared = merge_question_fragments(explode_utterances(utterances))
    turns: list[dict] = []
    for index, item in enumerate(prepared):
        score = question_score(item["text"])
        if looks_like_short_reply(item["text"]):
            role = "interrogado"
        elif score >= 2:
            role = "interrogador"
        elif score <= -1:
            role = "interrogado"
        elif turns:
            role = "interrogado" if turns[-1]["role"] == "interrogador" else "interrogador"
        else:
            role = "interrogador" if score >= 1 or index == 0 else "interrogado"
        turns.append({**item, "role": role})
    return merge_same_role(turns)


def pair_exchanges(turns: list[dict]) -> list[dict]:
    exchanges: list[dict] = []
    pending: dict | None = None
    for turn in turns:
        if turn["role"] == "interrogador":
            if pending and pending.get("answer"):
                exchanges.append(pending)
            pending = {
                "question": turn["text"],
                "answer": "",
                "start": turn["start"],
                "end": turn["end"],
                "answer_start": None,
                "answer_end": None,
            }
        elif pending is not None:
            if not pending.get("answer"):
                pending["answer_start"] = turn["start"]
            pending["answer"] = f"{pending['answer']} {turn['text']}".strip() if pending.get("answer") else turn["text"]
            pending["answer_end"] = turn["end"]
            pending["end"] = turn["end"]
        else:
            pending = {
                "question": "",
                "answer": turn["text"],
                "start": turn["start"],
                "end": turn["end"],
                "answer_start": turn["start"],
                "answer_end": turn["end"],
            }
    if pending and (pending.get("question") and pending.get("answer")):
        exchanges.append(pending)
    numbered = []
    for index, item in enumerate(exchanges, start=1):
        numbered.append({**item, "index": index})
    return numbered


def format_dialogue(turns: list[dict]) -> str:
    blocks: list[str] = []
    for turn in turns:
        label = "Interrogador" if turn["role"] == "interrogador" else "Interrogado"
        blocks.append(f"{label}: {turn['text']}")
    return "\n\n".join(blocks)


def _audio_slice(y: np.ndarray, sr: int, start: float, end: float, pad: float = 0.04) -> np.ndarray:
    i0 = max(0, int((max(0.0, start) - pad) * sr))
    i1 = min(len(y), max(i0 + 1, int((end + pad) * sr)))
    return y[i0:i1]


def _attach_comb_chart(
    row: dict,
    answer_y: np.ndarray,
    sr: int,
    a0: float,
    a1: float,
    comb_png: Path | None = None,
) -> dict:
    comb = comb_profile(answer_y, sr)
    duration = round(float(comb.get("duration") or max(0.0, a1 - a0)), 3)
    row["comb_samples"] = comb["samples"]
    row["comb_duration"] = duration
    row["comb_band_lo"] = comb.get("band_lo")
    row["comb_band_hi"] = comb.get("band_hi")
    if comb_png is not None and comb.get("available"):
        render_comb_png(comb["samples"], duration, comb_png)
    return row


def clip_comb_stale(row: dict) -> bool:
    samples = row.get("comb_samples") or []
    if len(samples) < 8:
        return True
    return float(min(samples)) < -0.02


def ensure_clip_combs(wav_path: str | Path, audio_id: str, interview: dict) -> bool:
    exchanges = list(interview.get("exchanges") or [])
    missing = [row for row in exchanges if clip_comb_stale(row)]
    if not missing:
        return False
    y, sr, _duration = _load_source_wav(wav_path)
    root = media_dir(audio_id) / "clips"
    for row in missing:
        a0 = float(row.get("answer_start") or row.get("start") or 0)
        a1 = float(row.get("answer_end") or row.get("end") or 0)
        answer_y = _audio_slice(y, sr, a0, a1)
        stem = f"{int(row.get('index') or 0):02d}"
        _attach_comb_chart(row, answer_y, sr, a0, a1, root / f"{stem}.comb.png")
    interview["exchanges"] = exchanges
    return True


def _answers_audio(y: np.ndarray, sr: int, turns: list[dict]) -> np.ndarray:
    chunks = [
        _audio_slice(y, sr, float(turn["start"]), float(turn["end"]))
        for turn in turns
        if turn.get("role") == "interrogado"
    ]
    return np.concatenate(chunks) if chunks else y


def _collect_utterances(stt: TranscriptionResult, duration: float) -> list[dict]:
    if stt.words:
        found = utterances_from_words(stt.words)
        if found:
            return found
    if stt.segments:
        found = [
            {
                "text": str(item.get("text") or "").strip(),
                "start": float(item.get("start") or 0),
                "end": float(item.get("end") or 0),
            }
            for item in stt.segments
            if str(item.get("text") or "").strip()
        ]
        if found:
            return found
    if stt.text:
        return [{"text": stt.text, "start": 0.0, "end": duration}]
    return []


def build_interview_view(wav_path: str | Path, stt: TranscriptionResult, audio_id: str) -> dict:
    wav_path = Path(wav_path)
    y, sr = sf.read(str(wav_path), always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = float(len(y) / sr) if sr else 0.0
    root = media_dir(audio_id)
    waveform_png = root / "waveform.png"

    utterances = _collect_utterances(stt, duration)
    if utterances:
        utterances = fill_untranscribed_replies(y, sr, utterances)
    turns = assign_roles(utterances) if utterances else []
    if turns:
        turns = relocate_short_replies(y, sr, turns, transcribe_fn=transcribe_clip)
        turns = snap_reply_bounds(y, sr, turns)
    exchanges = pair_exchanges(turns) if turns else []
    answers_y = _answers_audio(y, sr, turns)
    full_spectrum = microtremor_profile(answers_y, sr)
    render_waveform_png(y, sr, waveform_png, spectrum=full_spectrum)
    clip_rows: list[dict] = []
    for item in exchanges:
        if not item.get("question") or not item.get("answer"):
            continue
        if item["end"] <= item["start"]:
            continue
        stem = f"{item['index']:02d}"
        clip_wav = root / "clips" / f"{stem}.wav"
        clip_png = root / "clips" / f"{stem}.png"
        t0 = max(0.0, float(item["start"]) - 0.04)
        t1 = min(duration, float(item["end"]) + 0.04)
        if clip_rows:
            t0 = max(t0, float(clip_rows[-1]["answer_end"]) + 0.04)
            if t0 >= t1:
                t0 = max(0.0, t1 - 0.20)
        extract_clip(y, sr, t0, t1, clip_wav, pad=0.0)
        i0 = int(t0 * sr)
        i1 = max(i0 + 1, int(t1 * sr))
        clip_y = y[i0:i1]
        a0 = float(item.get("answer_start") or item["start"])
        a1 = float(item.get("answer_end") or item["end"])
        answer_y = _audio_slice(y, sr, a0, a1)
        clip_spectrum = microtremor_profile(answer_y, sr, chart_window=CHART_WINDOW)
        vsa_duration = round(float(clip_spectrum.get("duration") or max(0.0, a1 - a0)), 3)
        render_waveform_png(clip_y, sr, clip_png, width=720, height=120)
        render_vsa_png(clip_spectrum["mags"], vsa_duration, root / "clips" / f"{stem}.vsa.png")
        comb_png = root / "clips" / f"{stem}.comb.png"
        row = {
            "index": item["index"],
            "question": item["question"],
            "answer": item["answer"],
            "start": round(t0, 3),
            "end": round(t1, 3),
            "duration": round(t1 - t0, 3),
            "answer_start": round(a0, 3),
            "answer_end": round(a1, 3),
            "samples": envelope(clip_y, CLIP_ENVELOPE_BINS),
            "spectrum_mags": clip_spectrum["mags"],
            "spectrum_fmax": clip_spectrum["fmax"],
            "spectrum_peak_hz": clip_spectrum["peak_hz"],
            "spectrum_band_lo": clip_spectrum["band_lo"],
            "spectrum_band_hi": clip_spectrum["band_hi"],
            "spectrum_duration": vsa_duration,
            "include_vsa_in_report": False,
            "include_comb_in_report": False,
        }
        _attach_comb_chart(row, answer_y, sr, a0, a1, comb_png)
        clip_rows.append(row)

    answers = " ".join(row["answer"] for row in clip_rows if row.get("answer")).strip()
    dialogue = format_dialogue(turns)
    return {
        "has_dialogue": bool(turns),
        "transcript_dialogo": dialogue,
        "answers_text": answers,
        "turns": [
            {
                "role": turn["role"],
                "label": "Interrogador" if turn["role"] == "interrogador" else "Interrogado",
                "text": turn["text"],
                "start": round(float(turn["start"]), 3),
                "end": round(float(turn["end"]), 3),
            }
            for turn in turns
        ],
        "exchanges": clip_rows,
        "waveform": {
            "duration": round(duration, 3),
            "sample_rate": int(sr),
            "samples": envelope(y, ENVELOPE_BINS),
            "spectrum_mags": full_spectrum["mags"],
            "spectrum_fmax": full_spectrum["fmax"],
            "spectrum_peak_hz": full_spectrum["peak_hz"],
            "spectrum_band_lo": full_spectrum["band_lo"],
            "spectrum_band_hi": full_spectrum["band_hi"],
            "spectrum_duration": round(float(full_spectrum.get("duration") or 0.0), 3),
        },
    }


MIN_QUESTION_DUR = 0.20
MIN_ANSWER_DUR = 0.12
WINDOW_PAD = 2.5


def normalize_clip_bounds(
    start: float,
    end: float,
    answer_start: float | None,
    answer_end: float | None,
    duration: float,
) -> tuple[float, float, float, float]:
    span = duration if duration > 0 else 0.0
    start = max(0.0, min(float(start), span))
    end = max(0.0, min(float(end), span))
    need = MIN_QUESTION_DUR + MIN_ANSWER_DUR
    if end < start + need:
        end = min(span, start + need)
        if end - start < need:
            start = max(0.0, end - need)
    a0 = float(answer_start if answer_start is not None else max(start, end - 0.6))
    a1 = float(answer_end if answer_end is not None else end)
    a0 = min(max(a0, start), end - MIN_ANSWER_DUR)
    a1 = min(max(a1, a0 + MIN_ANSWER_DUR), end)
    return round(start, 3), round(end, 3), round(a0, 3), round(a1, 3)


def _load_source_wav(wav_path: str | Path) -> tuple[np.ndarray, int, float]:
    y, sr = sf.read(str(wav_path), always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    duration = float(len(y) / sr) if sr else 0.0
    return y, int(sr), duration


def build_clip_window(
    y: np.ndarray,
    sr: int,
    start: float,
    end: float,
    answer_start: float | None,
    answer_end: float | None,
    pad: float = WINDOW_PAD,
) -> dict:
    duration = float(len(y) / sr) if sr else 0.0
    start, end, a0, a1 = normalize_clip_bounds(start, end, answer_start, answer_end, duration)
    w0 = max(0.0, start - max(0.0, pad))
    w1 = min(duration, end + max(0.0, pad))
    if w1 <= w0:
        w1 = min(duration, w0 + 0.2)
    i0 = int(w0 * sr)
    i1 = max(i0 + 1, int(w1 * sr))
    return {
        "window_start": round(w0, 3),
        "window_end": round(w1, 3),
        "duration": round(w1 - w0, 3),
        "samples": envelope(y[i0:i1], CLIP_ENVELOPE_BINS),
        "start": start,
        "end": end,
        "answer_start": a0,
        "answer_end": a1,
    }


def write_clip_window_wav(
    y: np.ndarray,
    sr: int,
    window_start: float,
    window_end: float,
    dest: Path,
) -> Path:
    extract_clip(y, sr, window_start, window_end, dest, pad=0.0)
    return dest


def apply_manual_clip(
    wav_path: str | Path,
    audio_id: str,
    interview: dict,
    clip_index: int,
    start: float,
    end: float,
    answer_start: float | None,
    answer_end: float | None,
    language: str = "es",
    enable_praat: bool = True,
) -> dict:
    from app.services.vsa import attach_vsa_scores

    y, sr, duration = _load_source_wav(wav_path)
    start, end, a0, a1 = normalize_clip_bounds(start, end, answer_start, answer_end, duration)
    exchanges = list(interview.get("exchanges") or [])
    row = next((item for item in exchanges if int(item.get("index") or 0) == int(clip_index)), None)
    if row is None:
        raise ValueError("Clip no encontrado")
    root = media_dir(audio_id)
    stem = f"{int(clip_index):02d}"
    clip_wav = root / "clips" / f"{stem}.wav"
    clip_png = root / "clips" / f"{stem}.png"
    extract_clip(y, sr, start, end, clip_wav, pad=0.0)
    i0 = int(start * sr)
    i1 = max(i0 + 1, int(end * sr))
    clip_y = y[i0:i1]
    answer_y = _audio_slice(y, sr, a0, a1)
    clip_spectrum = microtremor_profile(answer_y, sr, chart_window=CHART_WINDOW)
    vsa_duration = round(float(clip_spectrum.get("duration") or max(0.0, a1 - a0)), 3)
    render_waveform_png(clip_y, sr, clip_png, width=720, height=120)
    render_vsa_png(clip_spectrum["mags"], vsa_duration, root / "clips" / f"{stem}.vsa.png")
    row.update(
        {
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "answer_start": a0,
            "answer_end": a1,
            "samples": envelope(clip_y, CLIP_ENVELOPE_BINS),
            "spectrum_mags": clip_spectrum["mags"],
            "spectrum_fmax": clip_spectrum["fmax"],
            "spectrum_peak_hz": clip_spectrum["peak_hz"],
            "spectrum_band_lo": clip_spectrum["band_lo"],
            "spectrum_band_hi": clip_spectrum["band_hi"],
            "spectrum_duration": vsa_duration,
        }
    )
    _attach_comb_chart(row, answer_y, sr, a0, a1, root / "clips" / f"{stem}.comb.png")
    interview["exchanges"] = exchanges
    attach_vsa_scores(interview, wav_path, language=language, enable_praat=enable_praat)
    return interview


CHART_NOTE_MAX = 100


def _chart_note(value: str | None) -> str:
    return (value or "").strip()[:CHART_NOTE_MAX]


def apply_clip_chart_inclusion(
    interview: dict,
    clip_index: int,
    include_vsa: bool | None = None,
    include_comb: bool | None = None,
    vsa_note: str | None = None,
    comb_note: str | None = None,
) -> dict:
    exchanges = list(interview.get("exchanges") or [])
    row = next((item for item in exchanges if int(item.get("index") or 0) == int(clip_index)), None)
    if row is None:
        raise ValueError("Clip no encontrado")
    if include_vsa is None and include_comb is None and vsa_note is None and comb_note is None:
        raise ValueError("Indique si la gráfica VSA o peine entra al informe")
    if include_vsa is not None:
        row["include_vsa_in_report"] = bool(include_vsa)
    if include_comb is not None:
        row["include_comb_in_report"] = bool(include_comb)
    if vsa_note is not None:
        row["vsa_report_note"] = _chart_note(vsa_note)
    if comb_note is not None:
        row["comb_report_note"] = _chart_note(comb_note)
    interview["exchanges"] = exchanges
    return interview


def apply_clip_text(interview: dict, clip_index: int, question: str, answer: str, language: str = "es") -> dict:
    from app.services.nlp import linguistic_features, linguistic_risk_score
    from app.services.vsa import KIND_LABELS, apply_baseline, classify_question_kind

    q = (question or "").strip()
    a = (answer or "").strip()
    if not q:
        raise ValueError("La pregunta no puede quedar vacía")
    if not a:
        raise ValueError("La respuesta no puede quedar vacía")

    exchanges = list(interview.get("exchanges") or [])
    row = next((item for item in exchanges if int(item.get("index") or 0) == int(clip_index)), None)
    if row is None:
        raise ValueError("Clip no encontrado")

    kind = classify_question_kind(q)
    kind_label = KIND_LABELS[kind]
    ling_feat = linguistic_features(a, language=language)
    ling_score, _ = linguistic_risk_score(ling_feat)
    row["question"] = q
    row["answer"] = a
    row["kind"] = kind
    row["kind_label"] = kind_label
    row["linguistic_score"] = round(float(ling_score), 4)

    vsa = dict(interview.get("vsa") or {})
    items = list(vsa.get("items") or [])
    for item in items:
        if int(item.get("index") or 0) != int(clip_index):
            continue
        fm = float(item.get("fm_stress") or row.get("fm_stress") or 0)
        aco = float(item.get("acoustic_score") or row.get("acoustic_score") or 0)
        item["question"] = q
        item["answer"] = a
        item["kind"] = kind
        item["kind_label"] = kind_label
        item["linguistic_score"] = round(float(ling_score), 4)
        item["vsa_score"] = round(0.40 * fm + 0.35 * aco + 0.25 * ling_score, 4)
        row["vsa_score"] = item["vsa_score"]
        row["fm_stress"] = fm
        row["acoustic_score"] = aco
        break

    if items:
        summary = apply_baseline(items)
        interview["vsa"] = {**vsa, **summary}
        by_index = {item.get("index"): item for item in summary.get("items") or []}
        for exchange in exchanges:
            extra = by_index.get(exchange.get("index")) or {}
            if not extra:
                continue
            exchange["kind"] = extra.get("kind", exchange.get("kind"))
            exchange["kind_label"] = extra.get("kind_label", exchange.get("kind_label"))
            exchange["vsa_score"] = extra.get("vsa_score", exchange.get("vsa_score"))
            exchange["delta"] = extra.get("delta")
            exchange["flagged"] = extra.get("flagged")

    interview["exchanges"] = exchanges
    interview["answers_text"] = " ".join(str(item.get("answer") or "") for item in exchanges).strip()
    _sync_turns_text(list(interview.get("turns") or []), row, q, a)
    return interview


def _sync_turns_text(turns: list[dict], row: dict, question: str, answer: str) -> None:
    q0 = float(row.get("start") or 0)
    a0 = float(row.get("answer_start") or q0)
    a1 = float(row.get("answer_end") or row.get("end") or a0)
    for turn in turns:
        mid = (float(turn.get("start") or 0) + float(turn.get("end") or 0)) / 2
        role = turn.get("role")
        if role == "interrogador" and q0 - 0.2 <= mid <= a0 + 0.15:
            turn["text"] = question
        elif role == "interrogado" and a0 - 0.15 <= mid <= a1 + 0.25:
            turn["text"] = answer
