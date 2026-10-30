"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";

type AuditRow = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<AuditRow[]>("/api/v1/audit")
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : "No se pudo leer la bitácora"));
  }, []);

  return (
    <Shell title="Auditoría" subtitle="Bitácora de accesos, colas y resultados">
      {error ? <p className="form-error">{error}</p> : null}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Acción</th>
              <th>Recurso</th>
              <th>Id</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="num">{new Date(row.created_at).toLocaleString("es")}</td>
                <td>{row.action}</td>
                <td>{row.resource_type}</td>
                <td>{row.resource_id || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
