"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

interface AreaComboboxProps {
  areas: string[];
  value: string | null;
  onChange: (area: string) => void;
  placeholder: string;
  dotColor: string;
}

export default function AreaCombobox({ areas, value, onChange, placeholder, dotColor }: AreaComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const filtered = useMemo(() => {
    if (!query) return areas;
    const q = query.toLowerCase();
    return areas.filter((a) => a.toLowerCase().includes(q));
  }, [areas, query]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-left text-sm text-ink transition hover:border-ink/30"
      >
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: dotColor }} />
        <span className={value ? "flex-1 truncate font-medium" : "flex-1 truncate text-muted"}>
          {value ?? placeholder}
        </span>
        <ChevronDown size={16} className="shrink-0 text-muted" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-[1100] max-h-64 overflow-auto rounded-xl border border-line bg-surface p-1.5 shadow-floating">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search areas..."
            className="mb-1 w-full rounded-lg border border-line px-2.5 py-1.5 text-sm outline-none focus:border-ink/40"
          />
          {filtered.length === 0 && (
            <p className="px-2.5 py-2 text-sm text-muted">No matching areas.</p>
          )}
          {filtered.map((area) => (
            <button
              key={area}
              type="button"
              onClick={() => {
                onChange(area);
                setOpen(false);
                setQuery("");
              }}
              className={`block w-full rounded-lg px-2.5 py-2 text-left text-sm transition hover:bg-canvas ${
                area === value ? "bg-canvas font-medium" : ""
              }`}
            >
              {area}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
