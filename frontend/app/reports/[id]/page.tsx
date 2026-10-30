"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ClipDialogue from "@/components/ClipDialogue";
import Shell from "@/components/Shell";
import SpeechWaveform from "@/components/SpeechWaveform";
import { InterviewExchange, InterviewTurn, Report, VsaItem, api, getToken } from "@/lib/api";

function clipTarget(turn: InterviewTurn, exchanges: InterviewExchange[]): { index: number; part: "q" | "a" } | null {
  const mid = (Number(turn.start) + Number(turn.end)) / 2;
  const isQuestion = turn.role === "interrogador";
  let best: InterviewExchange | null = null;
  let bestDist = Infinity;
  for (const clip of exchanges) {
    const q0 = clip.start;
    const a0 = clip.answer_start ?? clip.start;
    const a1 = clip.answer_end ?? clip.end;
    const inQuestion = mid >= q0 - 0.2 && mid <= a0 + 0.15;
    const inAnswer = mid >= a0 - 0.15 && mid <= a1 + 0.25;
    if ((isQuestion && inQuestion) || (!isQuestion && inAnswer)) {
      const dist = isQuestion ? Math.abs(mid - q0) : Math.abs(mid - a0);
      if (dist < bestDist) {
        best = clip;
        bestDist = dist;
      }
    }
  }
  if (best) return { index: best.index, part: isQuestion ? "q" : "a" };
  const text = (turn.text || "").trim().toLowerCase();
  if (!text) return null;
  const found = exchanges.find((clip) =>
    isQuestion ? (clip.question || "").trim().toLowerCase() === text : (clip.answer || "").trim().toLowerCase() === text,
  );
  return found ? { index: found.index, part: isQuestion ? "q" : "a" } : null;
}

async function download(path: string, filename: string) {
  const token = getToken();
  const response = await fetch(`/backend${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new Error("No se pudo descargar");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function kindBadge(kind?: string, flagged?: boolean) {
  if (flagged) return "badge fail";
  if (kind === "control") return "badge ok";
  if (kind === "stimulus") return "badge queued";
  return "badge warn";
}

function barColor(kind: string, flagged: boolean) {
  if (flagged) return "#DC2626";
  if (kind === "control") return "#22C55E";
  if (kind === "stimulus") return "#3B82F6";
  return "#F59E0B";
}

type ChartPoint = {
  name: string;
  v: number;
  kind: string;
  flagged: boolean;
  delta: number;
  question: string;
  answer: string;
};

function jumpToClip(index: string | number, part: "q" | "a") {
  const id = `clip-${index}-${part}`;
  const node = document.getElementById(id);
  node?.scrollIntoView({ behavior: "instant", block: "start" });
  history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
}

function ItemTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  if (x == null || y == null || !payload?.value) return null;
  return (
    <g
      className="chart-tick-link"
      role="link"
      tabIndex={0}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        jumpToClip(payload.value, "q");
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          jumpToClip(payload.value, "q");
        }
      }}
    >
      <title>{`Ir a la pregunta ${payload.value}`}</title>
      <text x={x} y={y} dy={14} textAnchor="middle" fill="#93c5fd" fontSize={12} fontWeight={600}>
        {payload.value}
      </text>
    </g>
  );
}

function ItemTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartPoint }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <span>Ítem {item.name}</span>
      <strong>{item.v.toFixed(2)}</strong>
      <em>
        {item.flagged ? "Sobre línea base" : `Δ ${item.delta >= 0 ? "+" : ""}${item.delta.toFixed(2)}`}
      </em>
      {item.question ? <small>{item.question}</small> : null}
      <div className="chart-tooltip-links">
        <a
          href={`#clip-${item.name}-q`}
          onClick={(event) => {
            event.preventDefault();
            jumpToClip(item.name, "q");
          }}
        >
          Pregunta
        </a>
        <a
          className="to-answer"
          href={`#clip-${item.name}-a`}
          onClick={(event) => {
            event.preventDefault();
            jumpToClip(item.name, "a");
          }}
        >
          Respuesta
        </a>
      </div>
    </div>
  );
}

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.id) return;
    api<Report>(`/api/v1/reports/${params.id}`)
      .then(setReport)
      .catch((err) => setError(err.message));
  }, [params.id]);

  const findings = report?.findings?.findings || [];
  const interview = report?.findings?.interview;
  const waveform = interview?.waveform;
  const turns = interview?.turns || [];
  const exchanges = interview?.exchanges || [];
  const exam = report?.findings?.exam;
  const vsa = report?.findings?.vsa;
  const chart: ChartPoint[] = (vsa?.items || []).map((item: VsaItem) => ({
    name: `${item.index}`,
    v: item.vsa_score,
    kind: item.kind,
    flagged: item.flagged,
    delta: item.delta,
    question: item.question || "",
    answer: item.answer || "",
  }));

  return (
    <Shell
      title={exam?.evaluation_code ? `Informe ${exam.evaluation_code}` : "Informe de análisis"}
      subtitle={report?.findings?.summary}
    >
      {error ? <p className="form-error">{error}</p> : null}
      {!report ? (
        <p>Cargando expediente…</p>
      ) : (
        <>
          {vsa && vsa.flagged_count > 0 ? (
            <p className="alert critical">
              {vsa.flagged_count} ítem(s) sobre la línea base {vsa.baseline.toFixed(2)}. Revise los clips marcados.
            </p>
          ) : null}
          <section className="grid">
            <article className="card">
              <h3>Confiabilidad</h3>
              <div className="metric teal">{Math.round(report.reliability_index * 100)}%</div>
            </article>
            <article className="card">
              <h3>Índice de riesgo</h3>
              <div className={`metric ${report.deception_index >= 0.5 ? "danger" : "warn"}`}>
                {Math.round(report.deception_index * 100)}%
              </div>
            </article>
            <article className="card">
              <h3>Índice VSA</h3>
              <div className="metric">{vsa ? vsa.vsa_index.toFixed(2) : "—"}</div>
            </article>
            <article className="card">
              <h3>Línea base</h3>
              <div className="metric">{vsa ? vsa.baseline.toFixed(2) : "—"}</div>
              <p className="kpi-note">{vsa ? `${vsa.flagged_count} ítem(s) sobre el umbral` : "Sin clips VSA"}</p>
            </article>
          </section>
          <div className="page-actions">
            <button className="btn secondary" onClick={() => download(`/api/v1/reports/${report.id}/pdf`, `verisonar-${report.id}.pdf`)}>
              Descargar PDF
            </button>
            <button className="btn secondary" onClick={() => download(`/api/v1/reports/${report.id}/json`, `verisonar-${report.id}.json`)}>
              Descargar JSON
            </button>
          </div>
          {exam ? (
            <section className="card" style={{ marginTop: 16 }}>
              <h3>Ficha del examen</h3>
              <div className="ficha-grid">
                <table>
                  <tbody>
                    <tr>
                      <td>Número</td>
                      <td>{exam.evaluation_code || "—"}</td>
                    </tr>
                    <tr>
                      <td>Evaluado</td>
                      <td>{exam.subject_name || "—"}</td>
                    </tr>
                    <tr>
                      <td>Identificación</td>
                      <td>{exam.subject_document || "—"}</td>
                    </tr>
                    <tr>
                      <td>Lugar</td>
                      <td>{exam.location || "—"}</td>
                    </tr>
                  </tbody>
                </table>
                <table>
                  <tbody>
                    <tr>
                      <td>Modalidad</td>
                      <td>{exam.modality || "—"}</td>
                    </tr>
                    <tr>
                      <td>Finalidad</td>
                      <td>{exam.purpose || "—"}</td>
                    </tr>
                    <tr>
                      <td>Evaluador</td>
                      <td>{exam.evaluator_name || "—"}</td>
                    </tr>
                    <tr>
                      <td>Cargo</td>
                      <td>{exam.evaluator_title || "—"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
          {chart.length ? (
            <section className="card" style={{ marginTop: 16, height: 320 }}>
              <h3>Puntaje VSA por ítem</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart className="vsa-item-chart" data={chart} barCategoryGap="18%">
                  <CartesianGrid stroke="#1e3a5f" strokeDasharray="3 6" vertical={false} />
                  <XAxis dataKey="name" stroke="#94A3B8" axisLine={false} tickLine={false} tick={<ItemTick />} />
                  <YAxis domain={[0, 1]} stroke="#94A3B8" axisLine={false} tickLine={false} tick={{ fill: "#94A3B8", fontSize: 12 }} />
                  <Tooltip
                    cursor={{ fill: "rgba(248, 250, 252, 0.04)" }}
                    content={<ItemTooltip />}
                    wrapperStyle={{ outline: "none", pointerEvents: "auto" }}
                  />
                  {typeof vsa?.baseline === "number" ? (
                    <ReferenceLine y={vsa.baseline} stroke="#14B8A6" strokeDasharray="4 4" />
                  ) : null}
                  <Bar
                    dataKey="v"
                    radius={[6, 6, 0, 0]}
                    maxBarSize={42}
                    cursor="pointer"
                    onClick={(point) => {
                      const name = point && typeof point === "object" && "name" in point ? String(point.name) : "";
                      if (name) jumpToClip(name, "a");
                    }}
                  >
                    {chart.map((item) => (
                      <Cell key={item.name} fill={barColor(item.kind, item.flagged)} cursor="pointer" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p style={{ color: "var(--muted)", fontSize: 13 }}>{vsa?.note}</p>
            </section>
          ) : null}
          {waveform?.samples?.length ? (
            <section className="card" style={{ marginTop: 16 }}>
              <h3>Registro de audio</h3>
              <SpeechWaveform
                samples={waveform.samples}
                duration={waveform.duration}
                audioPath={`/api/v1/reports/${report.id}/audio`}
                title="Oscilograma · habla continua"
                spectrum={waveform.spectrum_mags}
                spectrumDuration={waveform.spectrum_duration}
                spectrumLabel="Respuesta de microtemblor · respuestas"
              />
            </section>
          ) : null}
          <section className="card" style={{ marginTop: 16 }}>
            <h3>Transcripción ({report.stt_engine || "sin motor"})</h3>
            {turns.length ? (
              <div className="dialogue">
                {turns.map((turn, index) => {
                  const target = clipTarget(turn, exchanges);
                  return (
                    <p key={`${turn.start}-${index}`}>
                      <span className={turn.role === "interrogador" ? "role-q" : "role-a"}>{turn.label}:</span>{" "}
                      {target ? (
                        <a
                          className="turn-link"
                          href={`#clip-${target.index}-${target.part}`}
                          title={target.part === "q" ? `Ir a la pregunta ${target.index}` : `Ir a la respuesta ${target.index}`}
                        >
                          {turn.text}
                        </a>
                      ) : (
                        turn.text
                      )}
                    </p>
                  );
                })}
              </div>
            ) : (
              <p>
                {report.transcription ||
                  "Sin transcripción. Coloque modelos Vosk/Whisper en /data/models para operación STT offline."}
              </p>
            )}
          </section>
          {exchanges.length ? (
            <section className="card" style={{ marginTop: 16 }}>
              <h3>Clips pregunta y respuesta</h3>
              <div className="clip-grid">
                {exchanges.map((clip) => (
                  <article className={`clip-card${clip.flagged ? " flagged" : ""}`} id={`clip-${clip.index}`} key={clip.index}>
                    <header>
                      <strong>
                        Clip {clip.index}{" "}
                        <span className={kindBadge(clip.kind, clip.flagged)}>{clip.kind_label || clip.kind || "ítem"}</span>
                      </strong>
                      <span>
                        {typeof clip.vsa_score === "number" ? `VSA ${clip.vsa_score.toFixed(2)} · ` : ""}
                        {clip.start.toFixed(1)}s – {clip.end.toFixed(1)}s
                      </span>
                    </header>
                    <ClipDialogue
                      reportId={report.id}
                      clipIndex={clip.index}
                      question={clip.question}
                      answer={clip.answer}
                      onReportUpdated={setReport}
                    />
                    <SpeechWaveform
                      samples={clip.samples}
                      duration={clip.duration}
                      audioPath={`/api/v1/reports/${report.id}/clips/${clip.index}/audio?v=${clip.start}-${clip.end}-${clip.answer_end ?? clip.end}`}
                      title={`Oscilograma · pregunta ${clip.index}`}
                      spectrum={clip.spectrum_mags}
                      spectrumDuration={clip.spectrum_duration}
                      spectrumLabel="Respuesta de microtemblor"
                      comb={clip.comb_samples}
                      combDuration={clip.comb_duration}
                      combOffset={(clip.answer_start ?? clip.start) - clip.start}
                      editable
                      reportId={report.id}
                      clipIndex={clip.index}
                      clipStart={clip.start}
                      clipEnd={clip.end}
                      answerStart={clip.answer_start ?? clip.start}
                      answerEnd={clip.answer_end ?? clip.end}
                      includeVsaInReport={clip.include_vsa_in_report === true}
                      includeCombInReport={clip.include_comb_in_report === true}
                      vsaReportNote={clip.vsa_report_note || ""}
                      combReportNote={clip.comb_report_note || ""}
                      onReportUpdated={setReport}
                    />
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          <section className="card" style={{ marginTop: 16 }}>
            <h3>Hallazgos</h3>
            <ul className="findings">
              {findings.map((item) => (
                <li key={item.code}>
                  <b>{item.title}</b> — {item.detail}
                  {item.evidence ? <div>Evidencia: {item.evidence}</div> : null}
                </li>
              ))}
            </ul>
          </section>
          {report.findings?.acoustic_features?.praat ? (
            <section className="card" style={{ marginTop: 16 }}>
              <h3>Fonética Praat</h3>
              <table>
                <tbody>
                  <tr>
                    <td>F0 medio</td>
                    <td>{report.findings.acoustic_features.pitch_mean_hz ?? "—"} Hz</td>
                  </tr>
                  <tr>
                    <td>HNR</td>
                    <td>{report.findings.acoustic_features.hnr_mean_db ?? "—"} dB</td>
                  </tr>
                  <tr>
                    <td>Jitter local</td>
                    <td>
                      {typeof report.findings.acoustic_features.jitter_local === "number"
                        ? `${(report.findings.acoustic_features.jitter_local * 100).toFixed(2)}%`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <td>Shimmer local</td>
                    <td>
                      {typeof report.findings.acoustic_features.shimmer_local === "number"
                        ? `${(report.findings.acoustic_features.shimmer_local * 100).toFixed(2)}%`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <td>Intensidad</td>
                    <td>{report.findings.acoustic_features.intensity_mean_db ?? "—"} dB</td>
                  </tr>
                  <tr>
                    <td>F1 / F2</td>
                    <td>
                      {report.findings.acoustic_features.formant_f1_hz ?? "—"} / {report.findings.acoustic_features.formant_f2_hz ?? "—"} Hz
                    </td>
                  </tr>
                </tbody>
              </table>
              <p style={{ color: "var(--muted)", fontSize: 13 }}>{report.findings.acoustic_features.note}</p>
            </section>
          ) : null}
          <p className="disclaimer">{report.findings?.disclaimer}</p>
        </>
      )}
    </Shell>
  );
}
