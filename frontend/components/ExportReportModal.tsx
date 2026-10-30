"use client";

import { useEffect, useMemo, useState } from "react";
import { InterviewExchange, getToken } from "@/lib/api";

type ExportReportModalProps = {
  reportId: string;
  exchanges: InterviewExchange[];
  onClose: () => void;
};

type ExportState = {
  exam: boolean;
  protocol: boolean;
  items: boolean;
  findings: boolean;
  clips: boolean;
  oscillogram: boolean;
  vsaChart: boolean;
  combChart: boolean;
  notes: boolean;
};

const INITIAL: ExportState = {
  exam: true,
  protocol: true,
  items: true,
  findings: true,
  clips: true,
  oscillogram: true,
  vsaChart: true,
  combChart: true,
  notes: true,
};

function snippet(value: string | undefined, max = 72): string {
  const text = (value || "").trim() || "—";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export default function ExportReportModal({ reportId, exchanges, onClose }: ExportReportModalProps) {
  const allIndexes = useMemo(() => exchanges.map((clip) => clip.index), [exchanges]);
  const [opts, setOpts] = useState<ExportState>(INITIAL);
  const [clipIndexes, setClipIndexes] = useState<number[]>(allIndexes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  function toggle<K extends keyof ExportState>(key: K) {
    setOpts((current) => {
      const next = { ...current, [key]: !current[key] };
      if (key === "clips" && current.clips) {
        next.oscillogram = false;
        next.vsaChart = false;
        next.combChart = false;
        next.notes = false;
      }
      if (key === "clips" && !current.clips) {
        next.oscillogram = true;
        next.vsaChart = true;
        next.combChart = true;
        next.notes = true;
      }
      return next;
    });
  }

  function toggleClip(index: number) {
    setClipIndexes((current) =>
      current.includes(index) ? current.filter((item) => item !== index) : [...current, index].sort((a, b) => a - b),
    );
  }

  async function createReport() {
    setBusy(true);
    setError("");
    try {
      const token = getToken();
      const response = await fetch(`/backend/api/v1/reports/${reportId}/pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          exam: opts.exam,
          protocol: opts.protocol,
          items: opts.items,
          findings: opts.findings,
          clips: opts.clips,
          oscillogram: opts.clips && opts.oscillogram,
          vsa_chart: opts.clips && opts.vsaChart,
          comb_chart: opts.clips && opts.combChart,
          notes: opts.clips && opts.notes,
          clip_indexes: opts.clips ? clipIndexes : [],
        }),
      });
      if (!response.ok) throw new Error("No se pudo crear el informe");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `verisonar-${reportId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el informe");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={() => !busy && onClose()}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-head">
          <div>
            <p className="login-kicker">Exportar</p>
            <h2 id="export-title">Crear informe</h2>
            <p>Marque las secciones y las respuestas que deben entrar al PDF.</p>
          </div>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
            Cerrar
          </button>
        </header>

        <div className="export-grid">
          <section>
            <h3>Secciones</h3>
            <label className="export-check">
              <input type="checkbox" checked={opts.exam} onChange={() => toggle("exam")} />
              1. Datos del examen
            </label>
            <label className="export-check">
              <input type="checkbox" checked={opts.protocol} onChange={() => toggle("protocol")} />
              2. Protocolo y línea base
            </label>
            <label className="export-check">
              <input type="checkbox" checked={opts.items} onChange={() => toggle("items")} />
              3. Resultados por ítem
            </label>
            <label className="export-check">
              <input type="checkbox" checked={opts.findings} onChange={() => toggle("findings")} />
              4. Hallazgos y transcripción
            </label>
            <label className="export-check">
              <input type="checkbox" checked={opts.clips} onChange={() => toggle("clips")} />
              5. Clips pregunta y respuesta
            </label>
            <div className={`export-nested${opts.clips ? "" : " is-disabled"}`}>
              <label className="export-check">
                <input
                  type="checkbox"
                  checked={opts.oscillogram}
                  disabled={!opts.clips}
                  onChange={() => toggle("oscillogram")}
                />
                5.1 Oscilograma
              </label>
              <label className="export-check">
                <input
                  type="checkbox"
                  checked={opts.vsaChart}
                  disabled={!opts.clips}
                  onChange={() => toggle("vsaChart")}
                />
                5.2 Gráfica VSA
              </label>
              <label className="export-check">
                <input
                  type="checkbox"
                  checked={opts.combChart}
                  disabled={!opts.clips}
                  onChange={() => toggle("combChart")}
                />
                5.3 Gráfica peine
              </label>
              <label className="export-check">
                <input type="checkbox" checked={opts.notes} disabled={!opts.clips} onChange={() => toggle("notes")} />
                5.4 Notas
              </label>
            </div>
          </section>

          <section className={!opts.clips ? "is-disabled" : ""}>
            <div className="export-answers-head">
              <h3>Respuestas seleccionadas</h3>
              <div className="export-mini-actions">
                <button type="button" disabled={!opts.clips || busy} onClick={() => setClipIndexes(allIndexes)}>
                  Todas
                </button>
                <button type="button" disabled={!opts.clips || busy} onClick={() => setClipIndexes([])}>
                  Ninguna
                </button>
              </div>
            </div>
            <div className="export-answers">
              {exchanges.length ? (
                exchanges.map((clip) => (
                  <label key={clip.index} className="export-check export-answer">
                    <input
                      type="checkbox"
                      checked={clipIndexes.includes(clip.index)}
                      disabled={!opts.clips}
                      onChange={() => toggleClip(clip.index)}
                    />
                    <span>
                      <strong>Clip {clip.index}</strong>
                      <em>{snippet(clip.question)}</em>
                      <small>{snippet(clip.answer, 60)}</small>
                    </span>
                  </label>
                ))
              ) : (
                <p className="export-empty">No hay clips en este expediente.</p>
              )}
            </div>
          </section>
        </div>

        {error ? <p className="form-error">{error}</p> : null}
        <footer className="modal-actions">
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="button" className="btn" onClick={() => void createReport()} disabled={busy}>
            {busy ? "Generando…" : "Crear informe"}
          </button>
        </footer>
      </div>
    </div>
  );
}
