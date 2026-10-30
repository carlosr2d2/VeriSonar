"use client";

import { PointerEvent, useEffect, useRef, useState } from "react";
import { ClipWindow, Report, api, authBlob } from "@/lib/api";

type HandleKey = "start" | "answerStart" | "end";

type SpeechWaveformProps = {
  samples: number[];
  duration: number;
  audioPath?: string;
  title?: string;
  spectrum?: number[] | null;
  spectrumDuration?: number;
  spectrumOffset?: number;
  spectrumLabel?: string;
  comb?: number[] | null;
  combDuration?: number;
  combOffset?: number;
  editable?: boolean;
  reportId?: string;
  clipIndex?: number;
  clipStart?: number;
  clipEnd?: number;
  answerStart?: number;
  answerEnd?: number;
  includeVsaInReport?: boolean;
  includeCombInReport?: boolean;
  vsaReportNote?: string;
  combReportNote?: string;
  onReportUpdated?: (report: Report) => void;
};

const CHART_NOTE_MAX = 100;

const INK = {
  paper: "#1a3a5c",
  mid: "#4a7aa8",
  wave: "#e2e8f0",
  muted: "#b6c4d6",
  question: "rgba(59, 130, 246, 0.22)",
  answer: "rgba(20, 184, 166, 0.24)",
  outside: "rgba(13, 23, 40, 0.28)",
  questionInk: "#bfdbfe",
  answerInk: "#99f6e4",
  handleQ: "#3b82f6",
  handleA: "#14b8a6",
  playhead: "#f59e0b",
  vsa: "#f1f5f9",
  time: "#4ade80",
};

function formatSecMs(seconds: number) {
  const msTotal = Math.max(0, Math.round(seconds * 1000));
  const s = Math.floor(msTotal / 1000);
  const ms = msTotal % 1000;
  return `${s}:${ms.toString().padStart(3, "0")}`;
}

function drawStartEndLabels(
  ctx: CanvasRenderingContext2D,
  left: number,
  right: number,
  y: number,
  startSec?: number | null,
  endSec?: number | null,
) {
  if (startSec == null || endSec == null || !Number.isFinite(startSec) || !Number.isFinite(endSec)) return;
  ctx.fillStyle = INK.time;
  ctx.font = "600 13px Inter, Segoe UI, sans-serif";
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillText(`Inicio ${formatSecMs(startSec)}`, left, y);
  ctx.textAlign = "right";
  ctx.fillText(`Fin ${formatSecMs(endSec)}`, right, y);
}

function drawOscillogram(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  samples: number[],
  duration: number,
  progress: number,
  viewStart: number,
  regions?: { start: number; answerStart: number; end: number } | null,
  handles?: boolean,
) {
  ctx.fillStyle = INK.paper;
  ctx.fillRect(0, 0, width, height);
  const mid = Math.floor(height / 2);
  const xAt = (t: number) => {
    if (duration <= 0) return 0;
    return Math.round(((t - viewStart) / duration) * (width - 1));
  };

  if (regions && duration > 0) {
    const q0 = xAt(regions.start);
    const a0 = xAt(regions.answerStart);
    const a1 = xAt(regions.end);
    ctx.fillStyle = INK.outside;
    ctx.fillRect(0, 0, Math.max(0, q0), height);
    ctx.fillRect(Math.min(width, a1), 0, width, height);
    ctx.fillStyle = INK.question;
    ctx.fillRect(q0, 0, Math.max(1, a0 - q0), height);
    ctx.fillStyle = INK.answer;
    ctx.fillRect(a0, 0, Math.max(1, a1 - a0), height);
    ctx.font = "600 11px Inter, Segoe UI, sans-serif";
    ctx.fillStyle = INK.questionInk;
    if (a0 - q0 > 54) ctx.fillText("Pregunta", q0 + 8, 16);
    ctx.fillStyle = INK.answerInk;
    if (a1 - a0 > 58) ctx.fillText("Respuesta", a0 + 8, 16);
  }

  ctx.strokeStyle = INK.mid;
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(width, mid);
  ctx.stroke();
  ctx.fillStyle = INK.wave;
  const bins = samples.length || 1;
  const amp = height / 2 - 8;
  for (let i = 0; i < bins; i += 1) {
    const x = Math.floor((i / bins) * width);
    const half = Math.max(1, Math.round(Math.abs(samples[i] || 0) * amp));
    ctx.fillRect(x, mid - half, Math.max(1, Math.ceil(width / bins)), half * 2);
  }

  if (regions && handles) {
    const marks: Array<{ t: number; color: string }> = [
      { t: regions.start, color: INK.handleQ },
      { t: regions.answerStart, color: INK.handleA },
      { t: regions.end, color: INK.handleA },
    ];
    for (const mark of marks) {
      const x = xAt(mark.t);
      ctx.fillStyle = mark.color;
      ctx.fillRect(x - 1, 0, 3, height);
      ctx.beginPath();
      ctx.moveTo(x - 6, 0);
      ctx.lineTo(x + 6, 0);
      ctx.lineTo(x, 10);
      ctx.closePath();
      ctx.fill();
    }
  }

  if (progress > 0 && progress <= 1) {
    const x = Math.min(width - 1, Math.round(progress * width));
    ctx.strokeStyle = INK.playhead;
    ctx.beginPath();
    ctx.moveTo(x, 4);
    ctx.lineTo(x, height - 4);
    ctx.stroke();
  }
  ctx.fillStyle = INK.muted;
  ctx.font = "11px Inter, Segoe UI, sans-serif";
  ctx.textAlign = "left";
  const step = duration > 30 ? 5 : duration > 12 ? 2 : duration > 2 ? 1 : duration > 0.8 ? 0.2 : 0.1;
  for (let t = 0; t <= duration + 0.01; t += step) {
    const abs = viewStart + t;
    const x = duration > 0 ? Math.round((t / duration) * (width - 1)) : 0;
    ctx.fillRect(x, height - 14, 1, 8);
    const label = abs >= 10 && step >= 1 ? abs.toFixed(0) : abs.toFixed(step < 1 ? 1 : 0);
    ctx.fillText(label, Math.max(0, x - 4), height - 2);
  }
}

function drawStressChart(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  samples: number[],
  duration: number,
  progress: number,
  startSec?: number | null,
  endSec?: number | null,
) {
  ctx.fillStyle = INK.paper;
  ctx.fillRect(0, 0, width, height);
  const left = 8;
  const right = width - 8;
  const top = 16;
  const baseline = height - 38;
  const innerW = right - left;
  const innerH = baseline - top;
  const n = Math.max(samples.length, 2);

  ctx.strokeStyle = INK.mid;
  ctx.beginPath();
  ctx.moveTo(left, baseline);
  ctx.lineTo(right, baseline);
  ctx.stroke();

  ctx.beginPath();
  ctx.strokeStyle = INK.vsa;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (let i = 0; i < n; i += 1) {
    const mag = Math.max(0, samples[i] || 0);
    const x = left + (i / (n - 1)) * innerW;
    const y = baseline - mag * innerH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = INK.muted;
  ctx.font = "11px Inter, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  const step = duration > 30 ? 5 : duration > 12 ? 2 : 1;
  for (let t = 0; t <= duration + 0.01; t += step) {
    const x = duration > 0 ? left + (t / duration) * innerW : left;
    ctx.fillRect(x, baseline, 1, 6);
    ctx.fillText(String(Math.round(t)), x, baseline + 14);
  }
  drawStartEndLabels(ctx, left, right, height - 6, startSec, endSec);

  if (progress > 0) {
    const x = left + Math.min(1, progress) * innerW;
    ctx.strokeStyle = INK.playhead;
    ctx.beginPath();
    ctx.moveTo(x, 4);
    ctx.lineTo(x, height - 4);
    ctx.stroke();
  }
}

function tickStep(duration: number) {
  if (duration > 2) return 0.5;
  if (duration > 0.8) return 0.2;
  if (duration > 0.3) return 0.1;
  if (duration > 0.12) return 0.05;
  return 0.02;
}

type TimeWindow = {
  baseStart: number;
  baseDuration: number;
  viewStart: number;
  viewDuration: number;
};

function applyTimeZoom(z: TimeWindow, frac: number, deltaY: number): TimeWindow {
  if (z.baseDuration <= 0) return z;
  const factor = deltaY < 0 ? 0.8 : 1.25;
  const minDur = Math.min(z.baseDuration, 0.08);
  const nextDur = Math.min(z.baseDuration, Math.max(minDur, z.viewDuration * factor));
  const anchor = z.viewStart + frac * z.viewDuration;
  const nextStart = Math.min(
    z.baseStart + z.baseDuration - nextDur,
    Math.max(z.baseStart, anchor - frac * nextDur),
  );
  return { ...z, viewStart: nextStart, viewDuration: nextDur };
}

function applyTimePan(z: TimeWindow, deltaFrac: number): TimeWindow {
  if (z.baseDuration <= 0 || z.viewDuration >= z.baseDuration - 1e-6) return z;
  const nextStart = Math.min(
    z.baseStart + z.baseDuration - z.viewDuration,
    Math.max(z.baseStart, z.viewStart - deltaFrac * z.viewDuration),
  );
  return { ...z, viewStart: nextStart };
}

function drawCombChart(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  samples: number[],
  duration: number,
  progress: number,
  startSec?: number | null,
  endSec?: number | null,
  axisOrigin = 0,
) {
  ctx.fillStyle = INK.paper;
  ctx.fillRect(0, 0, width, height);
  const left = 10;
  const right = width - 10;
  const top = 10;
  const baseline = height - 38;
  const innerW = right - left;
  const innerH = baseline - top;
  const n = Math.max(samples.length, 1);

  ctx.strokeStyle = INK.mid;
  ctx.lineWidth = 1;
  ctx.strokeRect(left + 0.5, top + 0.5, innerW, innerH);
  ctx.beginPath();
  ctx.moveTo(left, baseline);
  ctx.lineTo(right, baseline);
  ctx.stroke();

  ctx.beginPath();
  ctx.strokeStyle = INK.vsa;
  ctx.lineWidth = 1.25;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (let i = 0; i < n; i += 1) {
    const mag = Math.max(0, samples[i] || 0);
    const x = left + (i / Math.max(n - 1, 1)) * innerW;
    const y = baseline - mag * innerH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = INK.muted;
  ctx.font = "11px Inter, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  const step = tickStep(duration);
  const decimals = step < 0.1 ? 2 : 1;
  for (let t = 0; t <= duration + 1e-6; t += step) {
    const x = duration > 0 ? left + (t / duration) * innerW : left;
    ctx.fillRect(x, baseline, 1, 6);
    ctx.fillText((axisOrigin + t).toFixed(decimals), x, baseline + 14);
  }
  drawStartEndLabels(ctx, left, right, height - 6, startSec, endSec);

  if (progress > 0 && progress <= 1) {
    const x = left + progress * innerW;
    ctx.strokeStyle = INK.playhead;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, baseline);
    ctx.stroke();
  }
}

function tremorPlayhead(
  progress: number,
  duration: number,
  spectrumDuration?: number,
  spectrumOffset?: number,
) {
  if (!spectrumDuration || spectrumDuration <= 0) return progress;
  if (spectrumOffset == null) {
    return Math.abs(spectrumDuration - duration) < 0.15 ? progress : 0;
  }
  const t = progress * duration;
  const rel = (t - spectrumOffset) / spectrumDuration;
  if (rel < 0 || rel > 1) return 0;
  return rel;
}

function timeFromPointer(event: PointerEvent<HTMLCanvasElement>, viewStart: number, duration: number) {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(rect.width, 1)));
  return viewStart + x * duration;
}

function sliceEnvelope(
  samples: number[],
  baseStart: number,
  baseDuration: number,
  viewStart: number,
  viewDuration: number,
) {
  if (!samples.length || baseDuration <= 0) return samples;
  const rel0 = (viewStart - baseStart) / baseDuration;
  const rel1 = (viewStart + viewDuration - baseStart) / baseDuration;
  const i0 = Math.max(0, Math.floor(rel0 * samples.length));
  const i1 = Math.min(samples.length, Math.max(i0 + 2, Math.ceil(rel1 * samples.length)));
  return samples.slice(i0, i1);
}

export default function SpeechWaveform({
  samples,
  duration,
  audioPath,
  title = "Habla continua",
  spectrum,
  spectrumDuration,
  spectrumOffset,
  spectrumLabel = "Gráfica VSA · respuesta",
  comb,
  combDuration,
  combOffset,
  editable = false,
  reportId,
  clipIndex,
  clipStart = 0,
  clipEnd,
  answerStart,
  answerEnd,
  includeVsaInReport = false,
  includeCombInReport = false,
  vsaReportNote = "",
  combReportNote = "",
  onReportUpdated,
}: SpeechWaveformProps) {
  const waveRef = useRef<HTMLCanvasElement | null>(null);
  const specRef = useRef<HTMLCanvasElement | null>(null);
  const combRef = useRef<HTMLCanvasElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const dragRef = useRef<HandleKey | null>(null);
  const panRef = useRef<{ kind: "osc" | "comb"; lastX: number } | null>(null);
  const didPanRef = useRef(false);
  const [panKind, setPanKind] = useState<"osc" | "comb" | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [error, setError] = useState("");
  const [viewSamples, setViewSamples] = useState(samples);
  const [baseStart, setBaseStart] = useState(clipStart);
  const [baseDuration, setBaseDuration] = useState(duration);
  const [viewStart, setViewStart] = useState(clipStart);
  const [viewDuration, setViewDuration] = useState(duration);
  const zoomRef = useRef({
    baseStart: clipStart,
    baseDuration: duration,
    viewStart: clipStart,
    viewDuration: duration,
  });
  const combBaseStart = answerStart ?? clipStart;
  const combBaseDuration = combDuration && combDuration > 0 ? combDuration : 0;
  const [combViewStart, setCombViewStart] = useState(combBaseStart);
  const [combViewDuration, setCombViewDuration] = useState(combBaseDuration);
  const combZoomRef = useRef({
    baseStart: combBaseStart,
    baseDuration: combBaseDuration,
    viewStart: combBaseStart,
    viewDuration: combBaseDuration,
  });
  const [chartTab, setChartTab] = useState<"vsa" | "comb">("vsa");
  const [includeVsa, setIncludeVsa] = useState(includeVsaInReport);
  const [includeComb, setIncludeComb] = useState(includeCombInReport);
  const [vsaNote, setVsaNote] = useState(vsaReportNote);
  const [combNote, setCombNote] = useState(combReportNote);
  const noteRef = useRef<HTMLInputElement | null>(null);
  const focusNoteRef = useRef(false);
  const [bounds, setBounds] = useState({
    start: clipStart,
    answerStart: answerStart ?? clipStart,
    end: clipEnd ?? clipStart + duration,
  });

  const hasSpectrum = Boolean(spectrum?.some((mag) => Math.abs(mag) > 0.02));
  const hasComb = Boolean(comb?.some((value) => Math.abs(value) > 0.02));
  const bothCharts = hasSpectrum && hasComb;
  const activeChart = bothCharts ? chartTab : hasComb && !hasSpectrum ? "comb" : "vsa";
  const tremorDuration = spectrumDuration && spectrumDuration > 0 ? spectrumDuration : duration;
  const tremorProgress = tremorPlayhead(progress, duration, spectrumDuration, spectrumOffset);
  const combSpan = combBaseDuration;
  const combProgress = tremorPlayhead(progress, duration, combSpan || undefined, combOffset);
  const chartStart = answerStart ?? clipStart;
  const combAbsStart = combBaseStart;
  const combAbsEnd = combSpan > 0 ? combAbsStart + combSpan : (answerEnd ?? clipEnd ?? combAbsStart + duration);
  const combAbsTime = combAbsStart + combProgress * (combSpan || 1);
  const combViewProgress =
    combViewDuration > 0 ? (combAbsTime - combViewStart) / combViewDuration : combProgress;
  const regions = {
    start: bounds.start,
    answerStart: bounds.answerStart,
    end: bounds.end,
  };
  const showRegions = editable || answerStart != null;

  zoomRef.current = { baseStart, baseDuration, viewStart, viewDuration };
  combZoomRef.current = {
    baseStart: combAbsStart,
    baseDuration: combSpan,
    viewStart: combViewStart,
    viewDuration: combViewDuration,
  };

  useEffect(() => {
    setViewSamples(samples);
    setBaseStart(clipStart);
    setBaseDuration(duration);
    setViewStart(clipStart);
    setViewDuration(duration);
    setBounds({
      start: clipStart,
      answerStart: answerStart ?? clipStart,
      end: clipEnd ?? clipStart + duration,
    });
    setEditing(false);
    setError("");
    const span = combDuration && combDuration > 0 ? combDuration : 0;
    const origin = answerStart ?? clipStart;
    setCombViewStart(origin);
    setCombViewDuration(span);
  }, [samples, duration, clipStart, clipEnd, answerStart, answerEnd, audioPath, combDuration, comb]);

  useEffect(() => {
    setIncludeVsa(includeVsaInReport);
    setIncludeComb(includeCombInReport);
  }, [includeVsaInReport, includeCombInReport]);

  useEffect(() => {
    setVsaNote(vsaReportNote);
    setCombNote(combReportNote);
  }, [vsaReportNote, combReportNote]);

  useEffect(() => {
    if (!audioPath) return;
    let alive = true;
    let created: string | null = null;
    authBlob(audioPath)
      .then((url) => {
        if (!alive) {
          URL.revokeObjectURL(url);
          return;
        }
        created = url;
        setObjectUrl(url);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [audioPath]);

  useEffect(() => {
    const canvas = waveRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const absTime = baseStart + progress * baseDuration;
    const viewProgress = viewDuration > 0 ? (absTime - viewStart) / viewDuration : 0;
    drawOscillogram(
      ctx,
      canvas.width,
      canvas.height,
      sliceEnvelope(viewSamples, baseStart, baseDuration, viewStart, viewDuration),
      viewDuration,
      viewProgress,
      viewStart,
      showRegions ? regions : null,
      editing,
    );
  }, [
    viewSamples,
    viewDuration,
    progress,
    viewStart,
    baseStart,
    baseDuration,
    showRegions,
    editing,
    bounds.start,
    bounds.answerStart,
    bounds.end,
  ]);

  useEffect(() => {
    const canvas = waveRef.current;
    if (!canvas) return;
    const node = canvas;
    function onWheel(event: WheelEvent) {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(rect.width, 1)));
      const next = applyTimeZoom(zoomRef.current, frac, event.deltaY);
      zoomRef.current = next;
      setViewStart(next.viewStart);
      setViewDuration(next.viewDuration);
    }
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    const canvas = combRef.current;
    if (!canvas) return;
    const node = canvas;
    function onWheel(event: WheelEvent) {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(rect.width, 1)));
      const next = applyTimeZoom(combZoomRef.current, frac, event.deltaY);
      combZoomRef.current = next;
      setCombViewStart(next.viewStart);
      setCombViewDuration(next.viewDuration);
    }
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [hasComb]);

  useEffect(() => {
    const canvas = specRef.current;
    if (!canvas || !hasSpectrum || !spectrum) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    drawStressChart(
      ctx,
      canvas.width,
      canvas.height,
      spectrum,
      tremorDuration,
      tremorProgress,
      chartStart,
      chartStart + tremorDuration,
    );
  }, [spectrum, tremorDuration, tremorProgress, hasSpectrum, activeChart, chartStart]);

  useEffect(() => {
    const canvas = combRef.current;
    if (!canvas || !hasComb || !comb) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const span = combViewDuration > 0 ? combViewDuration : combSpan || duration;
    drawCombChart(
      ctx,
      canvas.width,
      canvas.height,
      sliceEnvelope(comb, combAbsStart, combSpan || duration, combViewStart, span),
      span,
      combViewProgress,
      combAbsStart,
      combAbsEnd,
      Math.max(0, combViewStart - combAbsStart),
    );
  }, [
    comb,
    combSpan,
    combViewProgress,
    hasComb,
    duration,
    activeChart,
    combAbsStart,
    combAbsEnd,
    combViewStart,
    combViewDuration,
  ]);

  function toggle() {
    const node = audioRef.current;
    if (!node) return;
    if (node.paused) {
      node.play().catch(() => undefined);
    } else {
      node.pause();
    }
  }

  function pausePlayback() {
    const node = audioRef.current;
    if (!node) return;
    node.pause();
    setPlaying(false);
  }

  async function startEdit() {
    if (!reportId || clipIndex == null) return;
    pausePlayback();
    setBusy(true);
    setBusyLabel("Cargando ventana de recorte…");
    setError("");
    try {
      const window = await api<ClipWindow>(`/api/v1/reports/${reportId}/clips/${clipIndex}/window?pad=2.5`);
      const url = await authBlob(`/api/v1/reports/${reportId}/clips/${clipIndex}/window-audio?pad=2.5`);
      setObjectUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setViewSamples(window.samples);
      setBaseStart(window.window_start);
      setBaseDuration(window.duration);
      setViewStart(window.window_start);
      setViewDuration(window.duration);
      setBounds({
        start: window.start,
        answerStart: window.answer_start,
        end: window.end,
      });
      setProgress(0);
      setEditing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo abrir el recorte");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  function cancelEdit() {
    setEditing(false);
    setError("");
    setViewSamples(samples);
    setBaseStart(clipStart);
    setBaseDuration(duration);
    setViewStart(clipStart);
    setViewDuration(duration);
    setBounds({
      start: clipStart,
      answerStart: answerStart ?? clipStart,
      end: clipEnd ?? clipStart + duration,
    });
    if (audioPath) {
      authBlob(audioPath)
        .then((url) => {
          setObjectUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
          });
        })
        .catch(() => undefined);
    }
  }

  async function applyEdit() {
    if (!reportId || clipIndex == null) return;
    pausePlayback();
    setBusy(true);
    setBusyLabel("Aplicando recorte y recalculando VSA…");
    setError("");
    try {
      const updated = await api<Report>(`/api/v1/reports/${reportId}/clips/${clipIndex}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: bounds.start,
          end: bounds.end,
          answer_start: bounds.answerStart,
          answer_end: bounds.end,
        }),
      });
      setEditing(false);
      onReportUpdated?.(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el recorte");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  function nearestHandle(t: number): HandleKey | null {
    const candidates: Array<[HandleKey, number]> = [
      ["start", bounds.start],
      ["answerStart", bounds.answerStart],
      ["end", bounds.end],
    ];
    let best: HandleKey | null = null;
    let dist = 0.12;
    for (const [key, value] of candidates) {
      const d = Math.abs(t - value);
      if (d < dist) {
        dist = d;
        best = key;
      }
    }
    const px = viewDuration > 0 ? (dist / viewDuration) * 1000 : 999;
    return px <= 14 ? best : null;
  }

  function clampBounds(next: { start: number; answerStart: number; end: number }) {
    const lo = baseStart;
    const hi = baseStart + baseDuration;
    let start = Math.min(Math.max(next.start, lo), hi - 0.32);
    let end = Math.min(Math.max(next.end, start + 0.32), hi);
    let answerStart = Math.min(Math.max(next.answerStart, start + 0.08), end - 0.12);
    return { start, answerStart, end };
  }

  function beginPan(kind: "osc" | "comb", event: PointerEvent<HTMLCanvasElement>) {
    panRef.current = { kind, lastX: event.clientX };
    didPanRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    setPanKind(kind);
  }

  function movePan(kind: "osc" | "comb", event: PointerEvent<HTMLCanvasElement>) {
    const pan = panRef.current;
    if (!pan || pan.kind !== kind) return false;
    const width = event.currentTarget.getBoundingClientRect().width;
    const dx = event.clientX - pan.lastX;
    pan.lastX = event.clientX;
    if (dx === 0) return true;
    didPanRef.current = true;
    const deltaFrac = dx / Math.max(width, 1);
    if (kind === "osc") {
      const next = applyTimePan(zoomRef.current, deltaFrac);
      zoomRef.current = next;
      setViewStart(next.viewStart);
    } else {
      const next = applyTimePan(combZoomRef.current, deltaFrac);
      combZoomRef.current = next;
      setCombViewStart(next.viewStart);
    }
    return true;
  }

  function endPan(event: PointerEvent<HTMLCanvasElement>) {
    if (!panRef.current) return;
    panRef.current = null;
    setPanKind(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onContextMenuCanvas(event: { ctrlKey: boolean; preventDefault: () => void }) {
    if (event.ctrlKey || didPanRef.current) {
      event.preventDefault();
      didPanRef.current = false;
    }
  }

  function onPointerDown(event: PointerEvent<HTMLCanvasElement>) {
    if (event.button === 2 && event.ctrlKey) {
      beginPan("osc", event);
      return;
    }
    if (event.button !== 0) return;
    const t = timeFromPointer(event, viewStart, viewDuration);
    if (editing) {
      const handle = nearestHandle(t);
      if (handle) {
        dragRef.current = handle;
        event.currentTarget.setPointerCapture(event.pointerId);
        return;
      }
    }
    const node = audioRef.current;
    if (!node || !node.duration) return;
    node.currentTime = Math.min(node.duration, Math.max(0, t - baseStart));
    node.play().catch(() => undefined);
  }

  function onPointerMove(event: PointerEvent<HTMLCanvasElement>) {
    if (movePan("osc", event)) return;
    const handle = dragRef.current;
    if (!handle) return;
    const t = timeFromPointer(event, viewStart, viewDuration);
    setBounds((prev) => {
      if (handle === "start") return clampBounds({ ...prev, start: t });
      if (handle === "answerStart") return clampBounds({ ...prev, answerStart: t });
      return clampBounds({ ...prev, end: t });
    });
  }

  function onPointerUp(event: PointerEvent<HTMLCanvasElement>) {
    endPan(event);
    if (dragRef.current) {
      dragRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    }
  }

  const questionDur = Math.max(0, bounds.answerStart - bounds.start);
  const answerDur = Math.max(0, bounds.end - bounds.answerStart);
  const includeActive = activeChart === "comb" ? includeComb : includeVsa;
  const activeNote = activeChart === "comb" ? combNote : vsaNote;
  const savedActiveNote = activeChart === "comb" ? combReportNote : vsaReportNote;
  const canToggleReportChart = Boolean(reportId) && clipIndex != null;

  useEffect(() => {
    if (!includeActive || !focusNoteRef.current) return;
    focusNoteRef.current = false;
    noteRef.current?.focus();
  }, [includeActive]);

  async function saveChartOptions(payload: {
    include_vsa?: boolean;
    include_comb?: boolean;
    vsa_note?: string;
    comb_note?: string;
  }) {
    if (!reportId || clipIndex == null) return;
    const updated = await api<Report>(`/api/v1/reports/${reportId}/clips/${clipIndex}/charts`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    onReportUpdated?.(updated);
  }

  async function toggleIncludeInReport(checked: boolean) {
    if (!reportId || clipIndex == null) return;
    const previous = includeActive;
    if (checked) focusNoteRef.current = true;
    if (activeChart === "comb") setIncludeComb(checked);
    else setIncludeVsa(checked);
    try {
      await saveChartOptions(activeChart === "comb" ? { include_comb: checked } : { include_vsa: checked });
    } catch {
      if (activeChart === "comb") setIncludeComb(previous);
      else setIncludeVsa(previous);
    }
  }

  async function saveActiveNote() {
    const next = activeNote.trim().slice(0, CHART_NOTE_MAX);
    if (next === (savedActiveNote || "").trim()) return;
    try {
      await saveChartOptions(activeChart === "comb" ? { comb_note: next } : { vsa_note: next });
    } catch {
      if (activeChart === "comb") setCombNote(combReportNote);
      else setVsaNote(vsaReportNote);
    }
  }

  return (
    <div className={`wave-stack${busy ? " is-busy" : ""}`}>
      {busy ? (
        <div className="wave-busy" role="status" aria-live="polite">
          <span className="wave-busy-spinner" aria-hidden />
          <strong>{busyLabel || "Procesando…"}</strong>
          <span>Espere a que termine el recorte.</span>
        </div>
      ) : null}
      <div className="wave-studio">
        <div className="wave-studio-bar">
          {objectUrl ? (
            <button type="button" className="wave-studio-btn" onClick={toggle}>
              {playing ? "Pausa" : "Play"}
            </button>
          ) : null}
          <span>{title}</span>
          {showRegions ? (
            <small>
              P {bounds.start.toFixed(2)}–{bounds.answerStart.toFixed(2)}s · R {bounds.answerStart.toFixed(2)}–
              {bounds.end.toFixed(2)}s
            </small>
          ) : (
            <em>{duration ? `${duration.toFixed(1)} s` : ""}</em>
          )}
          {editable && !editing ? (
            <button type="button" className="wave-studio-btn" onClick={startEdit} disabled={busy}>
              {busy ? "Cargando…" : "Ajustar recorte"}
            </button>
          ) : null}
          {editing ? (
            <>
              <button type="button" className="wave-studio-btn" onClick={cancelEdit} disabled={busy}>
                Cancelar
              </button>
              <button type="button" className="wave-studio-btn primary" onClick={applyEdit} disabled={busy}>
                {busy ? "Guardando…" : "Aplicar recorte"}
              </button>
            </>
          ) : null}
        </div>
        <canvas
          ref={waveRef}
          className={`wave-osc${editing ? " is-edit" : ""}${panKind === "osc" ? " is-pan" : ""}`}
          width={1000}
          height={140}
          title="Ctrl + rueda: zoom · Ctrl + botón derecho: desplazar"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onContextMenu={onContextMenuCanvas}
        />
        {editing ? (
          <p className="wave-studio-hint">
            Arrastre los bordes para incluir audio cortado. Pregunta {questionDur.toFixed(2)}s · respuesta {answerDur.toFixed(2)}s.
            La gráfica VSA se recalcula al aplicar.
          </p>
        ) : null}
        {error ? <p className="wave-studio-error">{error}</p> : null}
      </div>
      {hasSpectrum || hasComb ? (
        <div className="wave-studio">
          <div className={`wave-studio-bar${bothCharts ? " wave-chart-tabs" : ""}`}>
            {bothCharts ? (
              <>
                <button
                  type="button"
                  className={activeChart === "vsa" ? "is-active" : ""}
                  onClick={() => setChartTab("vsa")}
                >
                  Gráfica VSA
                </button>
                <button
                  type="button"
                  className={activeChart === "comb" ? "is-active" : ""}
                  onClick={() => setChartTab("comb")}
                >
                  Gráfica peine
                </button>
              </>
            ) : (
              <span>{hasComb ? "Gráfica peine · respuesta" : "Gráfica VSA · respuesta"}</span>
            )}
            <div className="wave-chart-meta">
              {canToggleReportChart ? (
                <label className="wave-chart-include">
                  Adicionar al informe
                  <input
                    type="checkbox"
                    checked={includeActive}
                    onChange={(event) => {
                      void toggleIncludeInReport(event.target.checked);
                    }}
                    aria-label={
                      activeChart === "comb"
                        ? "Adicionar gráfica peine al informe"
                        : "Adicionar gráfica VSA al informe"
                    }
                  />
                </label>
              ) : null}
              <em>
                {activeChart === "comb"
                  ? combSpan
                    ? `${combSpan.toFixed(2)} s · 70–400 Hz`
                    : ""
                  : tremorDuration
                    ? `${tremorDuration.toFixed(1)} s`
                    : ""}
              </em>
            </div>
          </div>
          {hasSpectrum ? (
            <canvas
              ref={specRef}
              className={`wave-spectrum${activeChart === "vsa" ? "" : " is-hidden"}`}
              width={1000}
              height={360}
            />
          ) : null}
          {hasComb ? (
            <canvas
              ref={combRef}
              className={`wave-comb${activeChart === "comb" ? "" : " is-hidden"}${panKind === "comb" ? " is-pan" : ""}`}
              width={1000}
              height={360}
              title="Ctrl + rueda: zoom · Ctrl + botón derecho: desplazar"
              onPointerDown={(event) => {
                if (event.button === 2 && event.ctrlKey) beginPan("comb", event);
              }}
              onPointerMove={(event) => {
                movePan("comb", event);
              }}
              onPointerUp={endPan}
              onPointerCancel={endPan}
              onContextMenu={onContextMenuCanvas}
            />
          ) : null}
          {canToggleReportChart && includeActive ? (
            <div className="wave-chart-note">
              <input
                ref={noteRef}
                type="text"
                maxLength={CHART_NOTE_MAX}
                value={activeNote}
                placeholder="Nota para el informe (máx. 100 caracteres)"
                aria-label={
                  activeChart === "comb" ? "Nota de la gráfica peine" : "Nota de la gráfica VSA"
                }
                onChange={(event) => {
                  const value = event.target.value.slice(0, CHART_NOTE_MAX);
                  if (activeChart === "comb") setCombNote(value);
                  else setVsaNote(value);
                }}
                onBlur={() => {
                  void saveActiveNote();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                }}
              />
              <small>
                {activeNote.length}/{CHART_NOTE_MAX}
              </small>
            </div>
          ) : null}
        </div>
      ) : null}
      {objectUrl ? (
        <audio
          ref={audioRef}
          src={objectUrl}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => {
            setPlaying(false);
            setProgress(0);
          }}
          onTimeUpdate={(event) => {
            const node = event.currentTarget;
            if (node.duration) setProgress(node.currentTime / node.duration);
          }}
        />
      ) : null}
    </div>
  );
}
