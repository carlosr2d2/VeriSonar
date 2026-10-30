from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from app.config import settings
from app.core.logging import get_logger

ProgressCb = Callable[[int, str | None], None]

logger = get_logger(__name__)

_whisper_model = None
_whisper_model_key: str | None = None

VAD_SHORT_REPLIES = {
    "onset": 0.32,
    "offset": 0.22,
    "min_speech_duration_ms": 80,
    "min_silence_duration_ms": 160,
    "speech_pad_ms": 180,
}


class TranscriptionResult:
    def __init__(
        self,
        text: str,
        engine: str,
        language: str,
        confidence: float | None = None,
        words: list[dict] | None = None,
        segments: list[dict] | None = None,
    ):
        self.text = text.strip()
        self.engine = engine
        self.language = language
        self.confidence = confidence
        self.words = words or []
        self.segments = segments or []


def transcribe_offline(
    wav_path: str | Path,
    language: str = "es",
    on_progress: ProgressCb | None = None,
) -> TranscriptionResult:
    """STT 100% local. Prioriza faster-whisper y usa Vosk solo como respaldo."""
    wav_path = Path(wav_path)
    if on_progress:
        on_progress(1, "Preparando transcripción")
    if settings.enable_whisper:
        result = _transcribe_whisper(wav_path, language, on_progress=on_progress)
        if result:
            return result
    if settings.enable_vosk and language.startswith("es"):
        result = _transcribe_vosk(wav_path, language, on_progress=on_progress)
        if result:
            return result
    logger.warning("stt_models_missing", path=str(wav_path))
    return TranscriptionResult(
        text="",
        engine="none",
        language=language,
        confidence=None,
    )


def _model_root() -> Path:
    return Path(settings.model_dir)


def _get_whisper_model():
    """Carga large-v3 una sola vez por proceso para reutilizarlo en huecos sí/no."""
    global _whisper_model, _whisper_model_key
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        logger.info("whisper_import_failed", error=str(exc))
        return None

    key = f"{settings.whisper_model_size}:cpu:int8"
    if _whisper_model is not None and _whisper_model_key == key:
        return _whisper_model

    cache = _model_root() / "whisper"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        model = WhisperModel(
            settings.whisper_model_size,
            device="cpu",
            compute_type="int8",
            download_root=str(cache),
            local_files_only=True,
        )
    except Exception:
        if settings.is_offline:
            logger.warning("whisper_unavailable_offline", size=settings.whisper_model_size)
            return None
        logger.info("whisper_local_missing_trying_download", size=settings.whisper_model_size)
        try:
            model = WhisperModel(
                settings.whisper_model_size,
                device="cpu",
                compute_type="int8",
                download_root=str(cache),
                local_files_only=False,
            )
        except Exception as exc:
            logger.warning("whisper_unavailable_offline", error=str(exc))
            return None
    _whisper_model = model
    _whisper_model_key = key
    return model


def transcribe_clip(
    audio: np.ndarray,
    language: str = "es",
    initial_prompt: str | None = None,
) -> str:
    """Transcribe un recorte corto (respuesta sí/no) sin VAD, para no tragársela."""
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if samples.size < 1600:
        return ""
    peak = float(np.max(np.abs(samples)))
    if peak > 1.0:
        samples = samples / peak
    model = _get_whisper_model()
    if model is None:
        return ""
    lang = "es" if language.startswith("es") else "en"
    kwargs = {
        "language": lang,
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "vad_filter": False,
        "condition_on_previous_text": False,
        "word_timestamps": False,
        "repetition_penalty": 1.15,
        "no_repeat_ngram_size": 2,
        "compression_ratio_threshold": 2.4,
        "no_speech_threshold": 0.3,
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    try:
        segments, _info = model.transcribe(samples, **kwargs)
        return " ".join((segment.text or "").strip() for segment in segments).strip()
    except Exception as exc:
        logger.warning("clip_transcribe_failed", error=str(exc))
        return ""


def _words_from_payload(payload: dict) -> tuple[str, list[dict]]:
    text = (payload.get("text") or "").strip()
    words: list[dict] = []
    for item in payload.get("result") or []:
        word = str(item.get("word") or "").strip()
        if not word:
            continue
        words.append(
            {
                "word": word,
                "start": float(item.get("start") or 0),
                "end": float(item.get("end") or 0),
                "conf": float(item.get("conf") or 0),
            }
        )
    if not text and words:
        text = " ".join(w["word"] for w in words)
    return text, words


def _transcribe_vosk(
    wav_path: Path,
    language: str,
    on_progress: ProgressCb | None = None,
) -> TranscriptionResult | None:
    model_dir = _model_root() / "vosk" / settings.vosk_model_name
    if not model_dir.exists():
        logger.info("vosk_model_absent", dir=str(model_dir))
        return None
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
        import json
        import wave

        SetLogLevel(-1)
        model = Model(str(model_dir))
        with wave.open(str(wav_path), "rb") as wf:
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            chunks: list[str] = []
            words: list[dict] = []
            segments: list[dict] = []
            total_frames = max(wf.getnframes(), 1)
            last_percent = -1
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                if on_progress:
                    percent = min(99, int(wf.tell() / total_frames * 100))
                    if percent > last_percent:
                        last_percent = percent
                        on_progress(percent, "Transcribiendo")
                if rec.AcceptWaveform(data):
                    text, piece = _words_from_payload(json.loads(rec.Result()))
                    if text:
                        chunks.append(text)
                        words.extend(piece)
                        if piece:
                            segments.append(
                                {"text": text, "start": piece[0]["start"], "end": piece[-1]["end"]}
                            )
            text, piece = _words_from_payload(json.loads(rec.FinalResult()))
            if text:
                chunks.append(text)
                words.extend(piece)
                if piece:
                    segments.append({"text": text, "start": piece[0]["start"], "end": piece[-1]["end"]})
        if on_progress:
            on_progress(100, "Transcripción lista")
        return TranscriptionResult(
            text=" ".join(part for part in chunks if part).strip(),
            engine="vosk",
            language=language,
            words=words,
            segments=segments,
        )
    except Exception as exc:
        logger.error("vosk_failed", error=str(exc))
        return None


def _transcribe_whisper(
    wav_path: Path,
    language: str,
    on_progress: ProgressCb | None = None,
) -> TranscriptionResult | None:
    if on_progress:
        on_progress(3, "Cargando modelo de transcripción")
    model = _get_whisper_model()
    if model is None:
        return None

    lang = "es" if language.startswith("es") else "en"
    if on_progress:
        on_progress(8, "Transcribiendo")
    raw_segments, info = model.transcribe(
        str(wav_path),
        language=lang,
        beam_size=5,
        vad_filter=True,
        vad_parameters=VAD_SHORT_REPLIES,
        word_timestamps=True,
        condition_on_previous_text=False,
        no_speech_threshold=0.45,
    )
    segments: list[dict] = []
    words: list[dict] = []
    chunks: list[str] = []
    duration = float(getattr(info, "duration", 0) or 0)
    last_percent = 8
    for segment in raw_segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        start = float(getattr(segment, "start", 0) or 0)
        end = float(getattr(segment, "end", start) or start)
        chunks.append(text)
        segments.append({"text": text, "start": start, "end": end})
        if on_progress and duration > 0:
            percent = min(99, max(8, int(end / duration * 100)))
            if percent > last_percent:
                last_percent = percent
                on_progress(percent, "Transcribiendo")
        for item in getattr(segment, "words", None) or []:
            word = str(getattr(item, "word", "") or "").strip()
            if not word:
                continue
            words.append(
                {
                    "word": word,
                    "start": float(getattr(item, "start", start) or start),
                    "end": float(getattr(item, "end", end) or end),
                    "conf": float(getattr(item, "probability", 0) or 0),
                }
            )
    if on_progress:
        on_progress(100, "Transcripción lista")
    return TranscriptionResult(
        text=" ".join(chunks).strip(),
        engine=f"faster-whisper-{settings.whisper_model_size}",
        language=getattr(info, "language", lang),
        confidence=float(getattr(info, "language_probability", 0) or 0) or None,
        words=words,
        segments=segments,
    )
