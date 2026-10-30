"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { Report, api } from "@/lib/api";

export default function ReportsPage() {
  const [rows, setRows] = useState<Report[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Report[]>("/api/v1/reports")
      .then(setRows)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <Shell title="Informes" subtitle="Expedientes VSA listos para revisión y descarga de auditoría">
      {error ? <p className="form-error">{error}</p> : null}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Expediente</th>
              <th>Confiabilidad</th>
              <th>Riesgo</th>
              <th>Motor STT</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const risk = Math.round(row.deception_index * 100);
              const riskClass = risk >= 50 ? "risk-high" : risk >= 30 ? "risk-mid" : "risk-low";
              const code = row.findings?.exam?.evaluation_code || row.id.slice(0, 8);
              return (
                <tr key={row.id}>
                  <td className="num">{new Date(row.created_at).toLocaleString("es")}</td>
                  <td>{code}</td>
                  <td className="num">{Math.round(row.reliability_index * 100)}%</td>
                  <td className={`num ${riskClass}`}>{risk}%</td>
                  <td>{row.stt_engine || "n/d"}</td>
                  <td>
                    <Link className="table-link" href={`/reports/${row.id}`}>
                      Abrir
                    </Link>
                  </td>
                </tr>
              );
            })}
            {!rows.length ? (
              <tr>
                <td colSpan={6}>No hay informes. Cree un análisis para generar el primero.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
