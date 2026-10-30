"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SessionUser, clearSession, getSession, getToken, roleLabel } from "@/lib/api";

export default function Shell({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: string }) {
  const path = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<SessionUser | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/");
      return;
    }
    setSession(getSession());
  }, [router]);

  const admin = session?.role === "admin";
  const links = [
    { href: "/dashboard", label: "Tablero" },
    { href: "/analyze", label: "Nuevo análisis" },
    { href: "/reports", label: "Informes" },
    ...(admin ? [{ href: "/users", label: "Usuarios" }, { href: "/audit", label: "Auditoría" }] : []),
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <em>Análisis forense de voz</em>
          <strong>VeriSonar</strong>
          <span>Auditoría VSA · LATAM</span>
        </div>
        <nav className="nav" aria-label="Principal">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className={path === link.href || path.startsWith(`${link.href}/`) ? "active" : ""}>
              {link.label}
            </Link>
          ))}
        </nav>
        {session ? (
          <div className="session-user">
            <strong>{session.full_name || session.email}</strong>
            <span>{roleLabel(session.role)}</span>
          </div>
        ) : null}
        <ThemeToggle />
        <button
          className="btn secondary"
          onClick={() => {
            clearSession();
            router.replace("/");
          }}
        >
          Cerrar sesión
        </button>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
