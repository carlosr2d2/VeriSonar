"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { Report, api } from "@/lib/api";

type ClipDialogueProps = {
  reportId: string;
  clipIndex: number;
  question: string;
  answer: string;
  onReportUpdated?: (report: Report) => void;
};

function resize(node: HTMLTextAreaElement | null) {
  if (!node) return;
  node.style.height = "auto";
  node.style.height = `${Math.max(node.scrollHeight, 22)}px`;
}

export default function ClipDialogue({
  reportId,
  clipIndex,
  question,
  answer,
  onReportUpdated,
}: ClipDialogueProps) {
  const questionRef = useRef<HTMLTextAreaElement | null>(null);
  const answerRef = useRef<HTMLTextAreaElement | null>(null);
  const skipBlur = useRef(false);
  const [q, setQ] = useState(question);
  const [a, setA] = useState(answer);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setQ(question);
    setA(answer);
    setError("");
  }, [question, answer]);

  useEffect(() => {
    resize(questionRef.current);
    resize(answerRef.current);
  }, [q, a]);

  async function save(nextQ: string, nextA: string) {
    const questionText = nextQ.trim();
    const answerText = nextA.trim();
    if (questionText === (question || "").trim() && answerText === (answer || "").trim()) return;
    if (!questionText || !answerText) {
      setQ(question);
      setA(answer);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api<Report>(`/api/v1/reports/${reportId}/clips/${clipIndex}/text`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: questionText, answer: answerText }),
      });
      onReportUpdated?.(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el texto");
      setQ(question);
      setA(answer);
    } finally {
      setBusy(false);
    }
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>, field: "q" | "a") {
    if (event.key === "Escape") {
      event.preventDefault();
      skipBlur.current = true;
      setQ(question);
      setA(answer);
      event.currentTarget.blur();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      skipBlur.current = true;
      const nextQ = field === "q" ? event.currentTarget.value : q;
      const nextA = field === "a" ? event.currentTarget.value : a;
      event.currentTarget.blur();
      void save(nextQ, nextA);
    }
  }

  return (
    <>
      <p id={`clip-${clipIndex}-q`} className="clip-anchor clip-anchor-q clip-line">
        <span className="role-q">Interrogador:</span>
        <textarea
          ref={questionRef}
          className="clip-edit clip-edit-q"
          value={q}
          rows={1}
          disabled={busy}
          aria-label={`Pregunta ${clipIndex}`}
          title="Editar pregunta"
          onChange={(event) => setQ(event.target.value)}
          onBlur={() => {
            if (skipBlur.current) {
              skipBlur.current = false;
              return;
            }
            void save(q, a);
          }}
          onKeyDown={(event) => onKey(event, "q")}
        />
      </p>
      <p id={`clip-${clipIndex}-a`} className="clip-anchor clip-anchor-a clip-line">
        <span className="role-a">Interrogado:</span>
        <textarea
          ref={answerRef}
          className="clip-edit clip-edit-a"
          value={a}
          rows={1}
          disabled={busy}
          aria-label={`Respuesta ${clipIndex}`}
          title="Editar respuesta"
          onChange={(event) => setA(event.target.value)}
          onBlur={() => {
            if (skipBlur.current) {
              skipBlur.current = false;
              return;
            }
            void save(q, a);
          }}
          onKeyDown={(event) => onKey(event, "a")}
        />
      </p>
      {busy ? <p className="clip-edit-status">Guardando texto…</p> : null}
      {error ? <p className="wave-studio-error">{error}</p> : null}
    </>
  );
}
