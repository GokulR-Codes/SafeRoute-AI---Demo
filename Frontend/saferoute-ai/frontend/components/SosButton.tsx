"use client";

import { useState } from "react";
import { Phone, X } from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import { triggerSos } from "@/lib/api";
import type { EmergencyRoute } from "@/lib/types";
import { formatDistance } from "@/lib/utils";

export default function SosButton() {
  const route = useSafeRouteStore((s) => s.route);
  const hour = useSafeRouteStore((s) => s.hour);
  const [result, setResult] = useState<EmergencyRoute | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSos() {
    const lat = route?.source.lat;
    const lng = route?.source.lng;
    if (lat === undefined || lng === undefined) return;
    setBusy(true);
    try {
      const data = await triggerSos(lat, lng, hour);
      setResult(data);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pointer-events-auto flex flex-col items-end gap-2">
      {result && (
        <div className="w-72 rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
          <div className="flex items-start justify-between">
            <p className="text-sm font-semibold text-ink">Nearest safe haven</p>
            <button onClick={() => setResult(null)} aria-label="Close">
              <X size={15} className="text-muted" />
            </button>
          </div>
          {result.error ? (
            <p className="mt-1 text-xs text-danger">{result.error}</p>
          ) : (
            <p className="mt-1 text-xs text-muted">
              {formatDistance(result.snapped_node_distance_m)} to nearest node &middot;{" "}
              {formatDistance(result.route.distance_m)} route to{" "}
              {result.selected_haven.type === "unspecified" ? "safe haven" : result.selected_haven.type}
            </p>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={handleSos}
        disabled={!route || busy}
        aria-label="SOS: route to nearest safe haven"
        className="flex h-14 w-14 items-center justify-center rounded-full bg-danger text-white shadow-floating transition disabled:opacity-40"
      >
        <Phone size={22} fill="white" />
      </button>
    </div>
  );
}
