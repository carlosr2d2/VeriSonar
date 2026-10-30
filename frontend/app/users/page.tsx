"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { DirectoryUser, api, isAdmin, roleLabel } from "@/lib/api";

export default function UsersPage() {
  const [rows, setRows] = useState<DirectoryUser[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAdmin()) {
      setError("Solo un administrador puede ver el directorio de usuarios.");
      return;
    }
    api<DirectoryUser[]>("/api/v1/users")
      .then(setRows)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <Shell title="Usuarios" subtitle="Directorio de analistas y administradores">
      {error ? <p className="form-error">{error}</p> : null}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.full_name}</td>
                <td>{row.email}</td>
                <td>
                  <span className={`badge ${row.role === "admin" ? "queued" : "ok"}`}>{roleLabel(row.role)}</span>
                </td>
                <td>
                  <span className={`badge ${row.is_active ? "ok" : "fail"}`}>{row.is_active ? "Activo" : "Inactivo"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
