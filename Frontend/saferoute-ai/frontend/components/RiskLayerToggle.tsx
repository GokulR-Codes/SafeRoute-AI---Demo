"use client";

import { Layers, LoaderCircle } from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import { useRiskFactors } from "@/lib/useRiskFactors";

// Small legend swatch.
function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export default function RiskLayerToggle() {
  const showRiskLayer = useSafeRouteStore((s) => s.showRiskLayer);
  const setShowRiskLayer = useSafeRouteStore((s) => s.setShowRiskLayer);
  // Same hook the map uses; the module-level cache means this shares one fetch.
  const { loading, error } = useRiskFactors(showRiskLayer);

  return (
    <div className="pointer-events-auto flex flex-col items-end gap-1.5">
      <button
        type="button"
        onClick={() => setShowRiskLayer(!showRiskLayer)}
        aria-pressed={showRiskLayer}
        className={`flex items-center gap-2 rounded-pill border px-3 py-2 text-xs font-semibold shadow-floating backdrop-blur transition ${
          showRiskLayer
            ? "border-ink bg-ink text-surface"
            : "border-line bg-surface/95 text-ink hover:border-ink/40"
        }`}
      >
        {loading ? <LoaderCircle size={14} className="animate-spin" /> : <Layers size={14} />}
        Risk layer
      </button>

      {showRiskLayer && !error && (
        <div className="flex items-center gap-2.5 rounded-pill border border-line bg-surface/95 px-3 py-1.5 text-[10px] font-medium text-muted shadow-floating backdrop-blur">
          <Swatch color="#2FAE4E" label="Low" />
          <Swatch color="#D98A16" label="Med" />
          <Swatch color="#E1483C" label="High" />
        </div>
      )}

      {showRiskLayer && error && (
        <div className="rounded-pill border border-line bg-surface/95 px-3 py-1.5 text-[10px] font-medium text-danger shadow-floating backdrop-blur">
          {error}
        </div>
      )}
    </div>
  );
}
