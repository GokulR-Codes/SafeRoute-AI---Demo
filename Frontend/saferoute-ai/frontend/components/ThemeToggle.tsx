"use client";

import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

type Theme = "light" | "dark";

export default function ThemeToggle() {
  // null until mounted so SSR and first client render agree (the real theme is
  // already applied to <html> by the inline script in layout.tsx).
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* private mode / storage disabled — theme just won't persist */
    }
    setTheme(next);
  }

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Light mode" : "Dark mode"}
      className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-full border border-line bg-surface/95 text-ink shadow-floating backdrop-blur transition hover:opacity-90"
    >
      {/* Before mount, theme is null: render nothing to avoid a wrong-icon flash. */}
      {theme !== null && (isDark ? <Sun size={17} /> : <Moon size={17} />)}
    </button>
  );
}
