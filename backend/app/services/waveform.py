from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.services.acoustic import write_pcm16_wav

logger = get_logger(__name__)

PAPER = (244, 241, 234)
INK = (92, 92, 92)
AXIS = (168, 164, 154)
TICK = (120, 116, 108)
SPECTRUM_FILL = (44, 44, 44)
SPECTRUM_LINE = (28, 28, 28)
SPECTRUM_BAND = (232, 220, 180)
TREMOR_BINS = 360
TREMOR_FMAX = 20.0
TREMOR_FS = 200.0
TREMOR_BAND = (8.0, 14.0)
TREMOR_GATE = 0.06
CHART_WINDOW = 2.4


def envelope(y: np.ndarray, bins: int) -> list[float]:
    if y.size == 0 or bins <= 0:
        return [0.0] * max(bins, 1)
    if y.size <= bins:
        peak = float(np.max(np.abs(y))) or 1.0
        padded = np.zeros(bins, dtype=np.float32)
        padded[: y.size] = np.abs(y) / peak
        return [float(v) for v in padded]
    hop = y.size / bins
    out: list[float] = []
    peak = 1e-9
    for i in range(bins):
        start = int(i * hop)
        end = int((i + 1) * hop)
        val = float(np.max(np.abs(y[start:end]))) if end > start else 0.0
        out.append(val)
        if val > peak:
            peak = val
    return [v / peak for v in out]


def _frame_rms(y: np.ndarray, sr: int, target_fs: float = TREMOR_FS) -> np.ndarray:
    hop = max(1, int(round(sr / target_fs)))
    n = len(y) // hop
    if n < 8:
        return np.array([], dtype=np.float64)
    frames = np.asarray(y[: n * hop], dtype=np.float64).reshape(n, hop)
    return np.sqrt(np.mean(frames * frames, axis=1))


def _trace_bins(duration: float, bins: int | None, chart: bool) -> int:
    if bins and bins > 4:
        return int(bins)
    if chart:
        return TREMOR_BINS
    return int(np.clip(duration * 80.0, 360, 1600))


def _center_in_window(y: np.ndarray, sr: int, window: float) -> tuple[np.ndarray, float]:
    need = max(int(round(window * sr)), 1)
    if y.size >= need:
        return y, float(y.size / sr)
    pad = need - y.size
    left = pad // 2
    return np.pad(y, (left, pad - left)), float(window)


def microtremor_profile(
    y: np.ndarray,
    sr: int,
    bins: int | None = None,
    chart_window: float | None = None,
) -> dict:
    """Gráfica VSA de la respuesta: pico relleno sobre la línea de base.

    Un brote breve (sin estrés) forma un pico agudo. Una emisión más
    larga o cargada forma un monte más ancho. La cresta lleva la
    textura del microtemblor 8–14 Hz.
    """
    duration = float(len(y) / sr) if sr else 0.0
    work = y
    if chart_window and sr > 0:
        work, duration = _center_in_window(y, sr, chart_window)
    count = _trace_bins(duration, bins, chart_window is not None)
    empty = {
        "mags": [0.0] * count,
        "fmin": 0.0,
        "fmax": duration,
        "peak_hz": 0.0,
        "band_lo": TREMOR_BAND[0],
        "band_hi": TREMOR_BAND[1],
        "available": False,
        "kind": "chart",
        "duration": duration,
    }
    rms = _frame_rms(work, sr)
    if rms.size < 8 or sr <= 0:
        return empty
    try:
        from scipy.ndimage import gaussian_filter1d
        from scipy.signal import butter, hilbert, sosfiltfilt
    except Exception as exc:
        logger.warning("tremor_scipy_unavailable", error=str(exc))
        return empty

    sigma = max(1.4, 0.03 * TREMOR_FS)
    energy = gaussian_filter1d(rms, sigma=sigma)
    peak = float(np.max(energy)) or 1.0
    shape = np.where(energy / peak < TREMOR_GATE, 0.0, energy / peak)

    texture = np.zeros_like(shape)
    if rms.size >= 48:
        try:
            sos = butter(2, list(TREMOR_BAND), btype="band", fs=TREMOR_FS, output="sos")
            band = sosfiltfilt(sos, rms - float(np.mean(rms)))
            tex = np.abs(hilbert(band))
            tex = gaussian_filter1d(tex, sigma=1.2)
            tmax = float(np.max(tex)) or 1.0
            texture = tex / tmax
        except Exception:
            texture = np.zeros_like(shape)

    pattern = np.clip(shape * (0.88 + 0.12 * texture), 0.0, 1.0)
    if float(np.max(pattern)) <= 0:
        return empty
    grid = np.linspace(0, pattern.size - 1, count)
    sampled = np.interp(grid, np.arange(pattern.size), pattern)
    sampled = sampled / (float(np.max(sampled)) or 1.0)
    return {
        "mags": [round(float(v), 4) for v in sampled],
        "fmin": 0.0,
        "fmax": duration,
        "peak_hz": 0.0,
        "band_lo": TREMOR_BAND[0],
        "band_hi": TREMOR_BAND[1],
        "available": True,
        "kind": "chart",
        "duration": duration,
    }


def spectral_profile(y: np.ndarray, sr: int, fmax: float = TREMOR_FMAX, bins: int = TREMOR_BINS) -> dict:
    return microtremor_profile(y, sr, bins=bins)


COMB_BAND = (70.0, 400.0)
COMB_BINS = 1400


def comb_profile(y: np.ndarray, sr: int, bins: int | None = None) -> dict:
    """Peine DecepTech: ciclos sobre el eje X, todo en Y positivo."""
    duration = float(len(y) / sr) if sr else 0.0
    count = int(bins) if bins and bins > 32 else COMB_BINS
    empty = {
        "samples": [0.0] * count,
        "duration": duration,
        "available": False,
        "kind": "comb",
        "band_lo": COMB_BAND[0],
        "band_hi": COMB_BAND[1],
    }
    if y.size < max(64, int(sr * 0.06)) or sr <= 0:
        return empty
    try:
        from scipy.ndimage import gaussian_filter1d
        from scipy.signal import butter, hilbert, sosfiltfilt
    except Exception as exc:
        logger.warning("comb_scipy_unavailable", error=str(exc))
        return empty
    nyq = float(sr) / 2.0
    lo = min(COMB_BAND[0], nyq * 0.35)
    hi = min(COMB_BAND[1], nyq * 0.48)
    if lo >= hi - 10:
        return empty
    try:
        sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
        filtered = sosfiltfilt(sos, np.asarray(y, dtype=np.float64))
    except Exception:
        return empty
    peak = float(np.max(np.abs(filtered))) or 1.0
    osc = np.clip(filtered / peak, -1.0, 1.0)
    sigma = max(4.0, 0.010 * float(sr))
    env = gaussian_filter1d(np.abs(hilbert(osc)), sigma=sigma)
    env = env / (float(np.max(env)) or 1.0)
    lifted = np.clip(env * (1.0 + 0.42 * osc), 0.0, None)
    lifted = lifted / (float(np.max(lifted)) or 1.0)
    grid = np.linspace(0, lifted.size - 1, count)
    sampled = np.interp(grid, np.arange(lifted.size), lifted)
    return {
        "samples": [round(float(v), 4) for v in sampled],
        "duration": round(duration, 3),
        "available": True,
        "kind": "comb",
        "band_lo": COMB_BAND[0],
        "band_hi": COMB_BAND[1],
    }


def render_vsa_png(
    samples: list[float],
    duration: float,
    dest: Path,
    width: int = 720,
    height: int = 160,
) -> Path:
    return render_comb_png(samples, duration, dest, width=width, height=height)


def render_comb_png(
    samples: list[float],
    duration: float,
    dest: Path,
    width: int = 720,
    height: int = 160,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = np.full((height, width, 3), PAPER, dtype=np.uint8)
    img[0, :] = INK
    img[height - 19, :] = INK
    img[:, 0] = INK
    img[:, width - 1] = INK
    inner_h = height - 20
    baseline = inner_h - 1
    amp = max(8, inner_h - 8)
    img[baseline, 1 : width - 1] = AXIS
    n = len(samples)
    prev: tuple[int, int] | None = None
    if n:
        for i, value in enumerate(samples):
            mag = max(0.0, float(value))
            x = min(width - 2, max(1, int(round((i / max(n - 1, 1)) * (width - 1)))))
            y = int(np.clip(baseline - mag * amp, 1, baseline))
            if prev is not None:
                _draw_line(img, prev[0], prev[1], x, y, SPECTRUM_LINE)
            prev = (x, y)
    if duration > 0:
        step = 0.1 if duration <= 0.8 else (0.2 if duration <= 2 else 0.5)
        t = 0.0
        axis_y = height - 19
        while t <= duration + 1e-6:
            x = min(width - 2, max(1, int(round((t / duration) * (width - 1)))))
            img[axis_y : min(height, axis_y + 6), x] = TICK
            t += step
    write_png_rgb(dest, img)
    return dest


def _draw_line(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    height, width, _ = img.shape
    for i in range(steps + 1):
        x = int(round(x0 + (x1 - x0) * i / steps))
        y = int(round(y0 + (y1 - y0) * i / steps))
        if 0 <= x < width and 0 <= y < height:
            img[y, x] = color
            if y + 1 < height:
                img[y + 1, x] = color


def _render_spectrum_panel(img: np.ndarray, spectrum: dict, y0: int) -> None:
    height, width, _ = img.shape
    panel = height - y0
    if panel < 24 or width < 8:
        return
    img[y0:, :] = PAPER
    mags = spectrum.get("mags") or []
    if not mags:
        return
    duration = float(spectrum.get("duration") or spectrum.get("fmax") or 0.0)
    inner = panel - 18
    baseline = y0 + inner
    amp = max(8, inner - 10)

    img[baseline, :] = AXIS
    n = len(mags)
    prev: tuple[int, int] | None = None
    for i, value in enumerate(mags):
        mag = max(0.0, float(value))
        x = min(width - 1, int(round((i / max(n - 1, 1)) * (width - 1))))
        y = int(np.clip(baseline - mag * amp, y0 + 2, height - 2))
        if prev is not None:
            _draw_line(img, prev[0], prev[1], x, y, SPECTRUM_LINE)
        prev = (x, y)

    if duration > 0:
        step = 1.0 if duration <= 12 else (2.0 if duration <= 30 else 5.0)
        t = 0.0
        while t <= duration + 1e-6:
            x = min(width - 1, int(round((t / duration) * (width - 1))))
            img[baseline : min(height, baseline + 6), x] = TICK
            t += step


def write_png_rgb(path: Path, pixels: np.ndarray) -> None:
    height, width, _ = pixels.shape
    raw = b"".join(b"\x00" + pixels[row].tobytes() for row in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def render_waveform_png(
    y: np.ndarray,
    sr: int,
    dest: Path,
    width: int = 1000,
    height: int = 180,
    spectrum: dict | None = None,
    spectrum_height: int = 160,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    show_spectrum = bool(spectrum and spectrum.get("available"))
    total_h = height + (spectrum_height if show_spectrum else 0)
    img = np.full((total_h, width, 3), PAPER, dtype=np.uint8)
    mid = height // 2
    img[mid, :] = AXIS
    env = envelope(y, width)
    amp = max(height // 2 - 10, 8)
    for x, value in enumerate(env):
        half = max(1, int(abs(value) * amp))
        img[mid - half : mid + half + 1, x] = INK
    duration = len(y) / sr if sr else 0.0
    if duration > 0:
        step = 1.0 if duration <= 12 else (2.0 if duration <= 30 else 5.0)
        t = 0.0
        while t <= duration + 1e-6:
            x = min(width - 1, int(round((t / duration) * (width - 1))))
            img[mid + 2 : mid + 8, x] = TICK
            t += step
    if show_spectrum and spectrum is not None:
        _render_spectrum_panel(img, spectrum, height)
    write_png_rgb(dest, img)
    return dest


def extract_clip(y: np.ndarray, sr: int, start: float, end: float, dest: Path, pad: float = 0.12) -> tuple[float, float]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = max(0.0, start - pad)
    t1 = min(len(y) / sr if sr else end, end + pad)
    i0 = int(t0 * sr)
    i1 = max(i0 + 1, int(t1 * sr))
    write_pcm16_wav(dest, y[i0:i1], sr)
    return t0, t1
