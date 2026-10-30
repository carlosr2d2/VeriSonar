"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, DemoAccount, login, roleLabel } from "@/lib/api";

const FALLBACK_ACCOUNTS: DemoAccount[] = [
  { email: "admin@verisonar.local", password: "VeriSonar.Admin1", full_name: "Administrador VeriSonar", role: "admin" },
  { email: "carlos.herrera@verisonar.local", password: "VeriSonar.Admin2", full_name: "Carlos Herrera", role: "admin" },
  { email: "ana.reyes@verisonar.local", password: "Analista.Reyes1", full_name: "Ana Reyes", role: "analyst" },
  { email: "luis.gomez@verisonar.local", password: "Analista.Gomez1", full_name: "Luis Gómez", role: "analyst" },
  { email: "maria.soto@verisonar.local", password: "Analista.Soto1", full_name: "María Soto", role: "analyst" },
  { email: "diego.perez@verisonar.local", password: "Analista.Perez1", full_name: "Diego Pérez", role: "analyst" },
  { email: "camila.rojas@verisonar.local", password: "Analista.Rojas1", full_name: "Camila Rojas", role: "analyst" },
  { email: "jorge.nunez@verisonar.local", password: "Analista.Nunez1", full_name: "Jorge Núñez", role: "analyst" },
  { email: "valentina.diaz@verisonar.local", password: "Analista.Diaz1", full_name: "Valentina Díaz", role: "analyst" },
  { email: "andres.castro@verisonar.local", password: "Analista.Castro1", full_name: "Andrés Castro", role: "analyst" },
];

export default function HomePage() {
  const router = useRouter();
  const [email, setEmail] = useState(FALLBACK_ACCOUNTS[0].email);
  const [password, setPassword] = useState(FALLBACK_ACCOUNTS[0].password);
  const [accounts, setAccounts] = useState<DemoAccount[]>(FALLBACK_ACCOUNTS);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/auth/demo-accounts`)
      .then(async (response) => {
        if (!response.ok) return;
        const data = (await response.json()) as DemoAccount[];
        if (Array.isArray(data) && data.length) setAccounts(data);
      })
      .catch(() => undefined);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión");
    } finally {
      setLoading(false);
    }
  }

  function pickAccount(account: DemoAccount) {
    setEmail(account.email);
    setPassword(account.password);
    setError("");
  }

  return (
    <div className="login-wrap">
      <div className="login-layout">
        <form className="login-card" onSubmit={onSubmit}>
          <p className="login-kicker">Plataforma de análisis</p>
          <h1>VeriSonar</h1>
          <p>Acceso para analistas y auditores. Evaluación VSA de entrevistas con trazabilidad de expediente.</p>
          <div className="field">
            <label>Correo</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
          </div>
          <div className="field">
            <label>Clave</label>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
          </div>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Verificando…" : "Acceder"}
          </button>
          <p className="disclaimer">
            Procesamiento local. Los resultados son indicios analíticos y no constituyen prueba de mentira.
          </p>
        </form>

        <section className="login-card directory-card">
          <h2>Directorio de cuentas</h2>
          <p>Seleccione una fila para cargar correo y clave. 2 administradores y 8 analistas.</p>
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Rol</th>
                <th>Correo</th>
                <th>Clave</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.email}>
                  <td>
                    <button className="account-pick" type="button" onClick={() => pickAccount(account)}>
                      {account.full_name}
                    </button>
                  </td>
                  <td>
                    <span className={`badge ${account.role === "admin" ? "queued" : "ok"}`}>{roleLabel(account.role)}</span>
                  </td>
                  <td>
                    <button className="account-pick" type="button" onClick={() => pickAccount(account)}>
                      {account.email}
                    </button>
                  </td>
                  <td>
                    <code>{account.password}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
