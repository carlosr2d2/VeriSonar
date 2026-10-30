"use client";

import { useTheme } from "@/components/ThemeProvider";
import { ThemeName } from "@/lib/theme";

const OPTIONS: { id: ThemeName; label: string }[] = [
  { id: "dark", label: "Oscuro" },
  { id: "light", label: "Claro" },
];

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="theme-toggle" role="group" aria-label="Tema de la interfaz">
      {OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          className={theme === option.id ? "is-active" : ""}
          aria-pressed={theme === option.id}
          onClick={() => setTheme(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
