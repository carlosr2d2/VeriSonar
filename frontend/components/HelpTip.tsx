"use client";

import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";

type HelpTipProps = {
  title: string;
  children: React.ReactNode;
};

export default function HelpTip({ title, children }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="help-tip-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Ayuda: ${title}`}
        onClick={() => setOpen(true)}
      >
        ?
      </button>
      {open && typeof document !== "undefined"
        ? createPortal(
            <div className="modal-backdrop help-backdrop" role="presentation" onClick={() => setOpen(false)}>
              <div
                className="modal-card help-card"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                onClick={(event) => event.stopPropagation()}
              >
                <header className="modal-head">
                  <div>
                    <p className="login-kicker">Ayuda</p>
                    <h2 id={titleId}>{title}</h2>
                  </div>
                  <button type="button" className="btn secondary" onClick={() => setOpen(false)}>
                    Cerrar
                  </button>
                </header>
                <div className="help-body">{children}</div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
