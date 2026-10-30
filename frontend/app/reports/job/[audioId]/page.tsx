"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import { AnalysisProgress, AnalyzeStatus, ProgressStage, api } from "@/lib/api";

const STAGE_META: Array<{ key: keyof AnalysisProgress; title: string }> = [
  { key: "conversion", title: "Conversión" },
  { key: "transcription", title: "Transcripción" },
  { key: "analysis", title: "Análisis" },
];

const EMPTY_STAGE: ProgressStage = { percent: 0, status: "pending", label: "En espera" };

const EMPTY_PROGRESS: AnalysisProgress = {
  conversion: { percent: 0, status: "pending", label: "En cola" },
  transcription: EMPTY_STAGE,
  analysis: EMPTY_STAGE,
};

const AUDIO_STATUS: Record<string, string> = {
  queued: "En cola",
  uploaded: "Recibido",
  transcribing: "Convirtiendo / transcribiendo",
  analyzing: "Analizando",
  completed: "Completado",
  failed: "Falló",
};

function stageClass(status: string) {
  if (status === "done") return "done";
  if (status === "error") return "error";
  if (status === "running") return "running";
  return "pending";
}

function ProgressBar({ title, stage }: { title: string; stage: ProgressStage }) {
  const percent = Math.max(0, Math.min(100, Number(stage.percent) || 0));
  return (
    <div className={`progress-row is-${stageClass(stage.status)}`}>
      <header>
        <strong>{title}</strong>
        <span>{percent}%</span>
      </header>
      <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label={title}>
        <div className={`progress-fill ${stageClass(stage.status)}`} style={{ width: `${percent}%` }} />
      </div>
      <p>{stage.label || "En espera"}</p>
    </div>
  );
}

export default function JobPage() {
  const params = useParams<{ audioId: string }>();
  const router = useRouter();
  const [status, setStatus] = useState<AnalyzeStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.audioId) return;
    let cancelled = false;
    let redirectTimer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const payload = await api<AnalyzeStatus>(`/api/v1/analyze/${params.audioId}`);
        if (cancelled) return;
        setStatus(payload);
        setError("");
        if (payload.report) {
          redirectTimer = setTimeout(() => {
            if (!cancelled) router.replace(`/reports/${payload.report!.id}`);
          }, 700);
          return "stop";
        }
        if (payload.audio.status === "failed") {
          return "stop";
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Error");
      }
      return "continue";
    }

    tick();
    const timer = setInterval(async () => {
      const result = await tick();
      if (result === "stop") clearInterval(timer);
    }, 1000);

    return () => {
      cancelled = true;
      clearInterval(timer);
      if (redirectTimer) clearTimeout(redirectTimer);
    };
  }, [params.audioId, router]);

  const progress = status?.progress || EMPTY_PROGRESS;
  const audioStatus = status?.audio.status || "queued";

  return (
    <Shell title="Procesando audio" subtitle="Conversión a WAV PCM 16 bits, transcripción y análisis VSA">
      {error ? <p className="form-error">{error}</p> : null}
      <div className="card progress-card">
        <p className="progress-file">
          {status?.audio.original_name || "Audio en cola"}
          <span>
            {AUDIO_STATUS[audioStatus] || audioStatus}
            {status?.task_state ? ` · ${status.task_state}` : ""}
          </span>
        </p>
        <div className="progress-stack">
          {STAGE_META.map((item) => (
            <ProgressBar key={item.key} title={item.title} stage={progress[item.key] || EMPTY_STAGE} />
          ))}
        </div>
        {audioStatus === "failed" ? (
          <p className="progress-note">El análisis falló. Revise los logs del worker.</p>
        ) : (
          <p className="progress-note">Esta vista se actualiza sola. No cierre la pestaña.</p>
        )}
      </div>
    </Shell>
  );
}
