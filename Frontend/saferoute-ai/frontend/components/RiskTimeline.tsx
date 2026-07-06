"use client";

import { useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import { generateRoute } from "@/lib/api";
import { formatHour } from "@/lib/utils";

export default function RiskTimeline() {
  const route = useSafeRouteStore((s) => s.route);
  const hour = useSafeRouteStore((s) => s.hour);
  const setHour = useSafeRouteStore((s) => s.setHour);
  const sourceArea = useSafeRouteStore((s) => s.sourceArea);
  const destArea = useSafeRouteStore((s) => s.destArea);
  const mode = useSafeRouteStore((s) => s.mode);
  const setRoute = useSafeRouteStore((s) => s.setRoute);
  const setError = useSafeRouteStore((s) => s.setError);
  const [dragLoading, setDragLoading] = useState(false);

  const hourlyRisk = route?.predictive_risk.hourly_risk;
  const safestHour = route?.predictive_risk.safest_hour;
  const riskiestHour = route?.predictive_risk.riskiest_hour;

  const bars = useMemo(() => {
    return Array.from({ length: 24 }, (_, h) => {
      const key = `hour_${String(h).padStart(2, "0")}`;
      const value = hourlyRisk?.[key] ?? 0.35;
      return { hour: h, key, value };
    });
  }, [hourlyRisk]);

  const maxValue = Math.max(...bars.map((b) => b.value), 0.01);

  async function selectHour(h: number) {
    setHour(h);
    if (!route || !sourceArea || !destArea) return;
    setDragLoading(true);
    try {
      const result = await generateRoute({ sourceArea, destArea, mode, hour: h });
      setRoute(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Couldn't update the route for that hour.");
    } finally {
      setDragLoading(false);
    }
  }

  return (
    <div className="pointer-events-auto rounded-card border border-line bg-surface/95 px-5 py-3.5 shadow-floating backdrop-blur">
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="flex items-center gap-1.5 font-medium text-ink">
          <Clock size={13} /> Now &middot; {formatHour(hour)}
        </span>
        {route && (
          <span className="hidden sm:inline">
            Safest {safestHour && formatHour(Number(safestHour.split("_")[1]))} &middot; Riskiest{" "}
            {riskiestHour && formatHour(Number(riskiestHour.split("_")[1]))}
          </span>
        )}
        {dragLoading && <span className="text-ink">Updating&hellip;</span>}
      </div>

      <div className="mt-2 flex h-14 items-end gap-[3px]">
        {bars.map((b) => {
          const isSelected = b.hour === hour;
          const isSafest = safestHour === b.key;
          const isRiskiest = riskiestHour === b.key;
          const heightPct = 18 + (b.value / maxValue) * 82;
          let color = "#D8D8D3";
          if (route) {
            color = isSelected ? "#14151A" : isRiskiest ? "#E1483C" : isSafest ? "#2FAE4E" : "#C9CBC5";
          }
          return (
            <button
              key={b.hour}
              type="button"
              onClick={() => selectHour(b.hour)}
              title={`${formatHour(b.hour)} \u2014 risk ${b.value.toFixed(2)}`}
              className="group relative flex-1 rounded-t-sm transition-all"
              style={{ height: `${heightPct}%`, backgroundColor: color }}
            >
              {isSelected && (
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-semibold text-ink">
                  {b.hour}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
