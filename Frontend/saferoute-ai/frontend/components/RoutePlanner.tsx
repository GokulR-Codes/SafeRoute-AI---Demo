"use client";

import { useState } from "react";
import { ArrowUpDown, Zap, ShieldCheck, Scale, HeartHandshake, LoaderCircle } from "lucide-react";
import AreaCombobox from "./AreaCombobox";
import { useSafeRouteStore } from "@/lib/store";
import { generateRoute } from "@/lib/api";
import type { RouteMode } from "@/lib/types";

const MODES: { id: RouteMode; label: string; icon: React.ElementType }[] = [
  { id: "fastest", label: "Fastest", icon: Zap },
  { id: "safest", label: "Safest", icon: ShieldCheck },
  { id: "balanced", label: "Balanced", icon: Scale },
  { id: "women_safety", label: "Women safety", icon: HeartHandshake },
];

export default function RoutePlanner() {
  const areas = useSafeRouteStore((s) => s.areas);
  const sourceArea = useSafeRouteStore((s) => s.sourceArea);
  const destArea = useSafeRouteStore((s) => s.destArea);
  const mode = useSafeRouteStore((s) => s.mode);
  const hour = useSafeRouteStore((s) => s.hour);
  const loading = useSafeRouteStore((s) => s.loading);
  const setSourceArea = useSafeRouteStore((s) => s.setSourceArea);
  const setDestArea = useSafeRouteStore((s) => s.setDestArea);
  const swapAreas = useSafeRouteStore((s) => s.swapAreas);
  const setMode = useSafeRouteStore((s) => s.setMode);
  const setLoading = useSafeRouteStore((s) => s.setLoading);
  const setError = useSafeRouteStore((s) => s.setError);
  const setRoute = useSafeRouteStore((s) => s.setRoute);

  const [localError, setLocalError] = useState<string | null>(null);

  const canGenerate = Boolean(sourceArea && destArea && !loading);

  async function handleGenerate() {
    if (!sourceArea || !destArea) {
      setLocalError("Pick a source and destination first.");
      return;
    }
    setLocalError(null);
    setError(null);
    setLoading(true);
    try {
      const result = await generateRoute({ sourceArea, destArea, mode, hour });
      setRoute(result);
    } catch (err: any) {
      const message = err?.response?.data?.detail ?? "Couldn't generate a route. Is the backend running?";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="pointer-events-auto w-[340px] rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
      <div className="relative flex flex-col gap-2">
        <AreaCombobox
          areas={areas}
          value={sourceArea}
          onChange={setSourceArea}
          placeholder="Choose source area"
          dotColor="#2F6FED"
        />
        <AreaCombobox
          areas={areas}
          value={destArea}
          onChange={setDestArea}
          placeholder="Choose destination area"
          dotColor="#E1483C"
        />
        <button
          type="button"
          onClick={swapAreas}
          aria-label="Swap source and destination"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full border border-line bg-surface p-1.5 shadow-sm transition hover:bg-canvas"
        >
          <ArrowUpDown size={14} className="text-muted" />
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {MODES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setMode(id)}
            className={`flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-xs font-medium transition ${
              mode === id
                ? "border-ink bg-ink text-white"
                : "border-line bg-surface text-ink hover:border-ink/40"
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {localError && <p className="mt-2 text-xs text-danger">{localError}</p>}

      <button
        type="button"
        onClick={handleGenerate}
        disabled={!canGenerate}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? (
          <>
            <LoaderCircle size={16} className="animate-spin" /> Generating route...
          </>
        ) : (
          "Generate route"
        )}
      </button>
    </div>
  );
}
