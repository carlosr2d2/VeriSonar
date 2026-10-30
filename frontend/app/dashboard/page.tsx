"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Shell from "@/components/Shell";
import { api, DashboardMetrics, Health, getSession } from "@/lib/api";

const BAR_COLORS: Record<string, string> = {
  Completados: "#14B8A6",
  "En curso": "#3B82F6",
  Fallidos: "#DC2626",
};

type LoadPoint = { name: string; v: number };

function LoadTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: LoadPoint }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <span>{item.name}</span>
      <strong>{item.v}</strong>
      <em>análisis</em>
    </div>
  );
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [subtitle, setSubtitle] = useState("Estado del laboratorio y de los workers Celery");

  useEffect(() => {
    setSubtitle(
      getSession()?.role === "analyst"
        ? "Sus expedientes, cola de análisis y estado operativo"
        : "Carga de análisis, indicadores VSA y salud de la plataforma",
    );
    api<DashboardMetrics>("/api/v1/dashboard")
      .then(setMetrics)
      .catch((err) => setError(err.message));
    fetch("/backend/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => undefined);
  }, []);

  const chart: LoadPoint[] = metrics
    ? [
        { name: "Completados", v: metrics.analyses_completed },
        { name: "En curso", v: metrics.analyses_in_progress },
        { name: "Fallidos", v: metrics.analyses_failed },
      ]
    : [];

  const failed = metrics?.analyses_failed ?? 0;
  const workers = metrics?.celery_workers ?? 0;
  const inProgress = metrics?.analyses_in_progress ?? 0;

  return (
    <Shell title="Tablero" subtitle={subtitle}>
      {error ? <p className="form-error">{error}</p> : null}
      {metrics && failed > 0 ? (
        <p className="alert critical">{failed} análisis fallido(s). Revise la cola y los logs del worker.</p>
      ) : metrics && workers < 1 ? (
        <p className="alert warn">No hay workers activos. El análisis nuevo permanecerá en cola.</p>
      ) : metrics && inProgress > 0 ? (
        <p className="alert">{inProgress} análisis en curso. La cola operativa está activa.</p>
      ) : null}
      <section className="grid">
        <article className="card">
          <h3>Confiabilidad media</h3>
          <div className="metric teal">{metrics ? `${Math.round(metrics.avg_reliability * 100)}%` : "—"}</div>
        </article>
        <article className="card">
          <h3>Índice de riesgo medio</h3>
          <div className={`metric ${metrics && metrics.avg_deception >= 0.5 ? "danger" : "warn"}`}>
            {metrics ? `${Math.round(metrics.avg_deception * 100)}%` : "—"}
          </div>
        </article>
        <article className="card">
          <h3>Workers</h3>
          <div className={`metric ${workers < 1 ? "danger" : ""}`}>{metrics?.celery_workers ?? "—"}</div>
          <p className="kpi-note">
            Activas {metrics?.celery_active_tasks ?? 0} · En cola {metrics?.celery_queued_tasks ?? 0}
          </p>
        </article>
        <article className="card">
          <h3>Expedientes</h3>
          <div className="metric">{metrics?.sessions_total ?? "—"}</div>
        </article>
      </section>

      <section className="card" style={{ marginTop: 20, height: 280 }}>
        <h3>Carga de análisis</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chart} barCategoryGap="28%">
            <CartesianGrid stroke="#23466F" strokeDasharray="3 6" vertical={false} />
            <XAxis
              dataKey="name"
              stroke="#94A3B8"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#94A3B8", fontSize: 12 }}
            />
            <YAxis
              stroke="#94A3B8"
              allowDecimals={false}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#94A3B8", fontSize: 12 }}
            />
            <Tooltip
              cursor={{ fill: "rgba(248, 250, 252, 0.04)" }}
              content={<LoadTooltip />}
              wrapperStyle={{ outline: "none" }}
            />
            <Bar dataKey="v" radius={[6, 6, 0, 0]} maxBarSize={64}>
              {chart.map((item) => (
                <Cell key={item.name} fill={BAR_COLORS[item.name]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="card" style={{ marginTop: 20 }}>
        <h3>Salud de la plataforma</h3>
        <p>
          Modo <b>{health?.processing_mode}</b> · versión {health?.version} · estado {health?.status}
        </p>
        <table>
          <thead>
            <tr>
              <th>Componente</th>
              <th>Estado</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {(health?.components || []).map((item) => (
              <tr key={item.name}>
                <td>{item.name}</td>
                <td>
                  <span className={`badge ${item.status === "ok" ? "ok" : item.status === "error" ? "fail" : "queued"}`}>
                    {item.status}
                  </span>
                </td>
                <td>{item.detail || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <p className="disclaimer">
        VeriSonar estima patrones lingüísticos y acústicos. No afirma que una persona mienta y no sustituye
        peritaje humano.
      </p>
    </Shell>
  );
}
