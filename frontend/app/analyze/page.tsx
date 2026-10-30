"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import { AnalyzeAccepted, getSession } from "@/lib/api";

export default function AnalyzePage() {
  const router = useRouter();
  const [title, setTitle] = useState("Entrevista VSA");
  const [language, setLanguage] = useState("es");
  const [context, setContext] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [subjectDocument, setSubjectDocument] = useState("");
  const [location, setLocation] = useState("");
  const [modality, setModality] = useState("presencial");
  const [purpose, setPurpose] = useState("");
  const [evaluatorName, setEvaluatorName] = useState("");
  const [evaluatorTitle, setEvaluatorTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const current = getSession();
    if (current?.full_name) setEvaluatorName(current.full_name);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Seleccione un audio WAV, MP3, OGG, WEBM, M4A o FLAC.");
      return;
    }
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("title", title);
    body.append("language", language);
    body.append("modality", modality);
    if (context) body.append("context", context);
    if (subjectName) body.append("subject_name", subjectName);
    if (subjectDocument) body.append("subject_document", subjectDocument);
    if (location) body.append("location", location);
    if (purpose) body.append("purpose", purpose);
    if (evaluatorName) body.append("evaluator_name", evaluatorName);
    if (evaluatorTitle) body.append("evaluator_title", evaluatorTitle);
    try {
      const token = localStorage.getItem("vs_token");
      const response = await fetch("/backend/api/v1/analyze", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "No se pudo encolar el audio");
      }
      const accepted = (await response.json()) as AnalyzeAccepted;
      router.push(`/reports/job/${accepted.audio_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de carga");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Nuevo análisis" subtitle="Registre la ficha, adjunte el audio y envíe el expediente a la cola VSA">
      <form className="card analyze-form" onSubmit={onSubmit}>
        <p className="section-label">Audio de entrevista</p>
        <div className="drop">
          <input
            type="file"
            accept="audio/*,.wav,.mp3,.ogg,.webm,.m4a,.flac,.amr,.3gp"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <p>{file ? file.name : "Arrastre o elija el audio de la entrevista"}</p>
        </div>
        <p className="section-label">Ficha del expediente</p>
        <div className="form-grid">
          <div className="field">
            <label>Título del expediente</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="field">
            <label>Idioma</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="es">Español latinoamericano</option>
              <option value="en">English (fase posterior — motor listo)</option>
            </select>
          </div>
          <div className="field">
            <label>Modalidad</label>
            <select value={modality} onChange={(e) => setModality(e.target.value)}>
              <option value="presencial">Presencial</option>
              <option value="remoto">Remoto</option>
            </select>
          </div>
          <div className="field">
            <label>Nombre del evaluado</label>
            <input value={subjectName} onChange={(e) => setSubjectName(e.target.value)} placeholder="Laura Méndez" />
          </div>
          <div className="field">
            <label>Identificación</label>
            <input value={subjectDocument} onChange={(e) => setSubjectDocument(e.target.value)} placeholder="Documento" />
          </div>
          <div className="field">
            <label>Lugar</label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Sala de entrevistas" />
          </div>
          <div className="field">
            <label>Finalidad</label>
            <input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Faltante de inventario" />
          </div>
          <div className="field">
            <label>Evaluador</label>
            <input value={evaluatorName} onChange={(e) => setEvaluatorName(e.target.value)} />
          </div>
          <div className="field">
            <label>Cargo del evaluador</label>
            <input value={evaluatorTitle} onChange={(e) => setEvaluatorTitle(e.target.value)} placeholder="Analista" />
          </div>
        </div>
        <div className="field">
          <label>Contexto (opcional)</label>
          <textarea rows={3} value={context} onChange={(e) => setContext(e.target.value)} />
        </div>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="btn" disabled={busy} type="submit">
          {busy ? "Encolando…" : "Enviar a análisis"}
        </button>
      </form>
    </Shell>
  );
}
