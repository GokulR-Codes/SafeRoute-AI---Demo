"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import { generateRoute } from "@/lib/api";
import { formatHour, formatISTClock, getISTHour } from "@/lib/utils";

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

  // Live IST clock. Initialized empty so server and client render the same
  // markup (avoids hydration mismatch), then filled + ticked on the client.
  const [nowHour, setNowHour] = useState<number | null>(null);
  const [nowClock, setNowClock] = useState<string>("");

  useEffect(() => {
    const tick = () => {
      setNowHour(getISTHour());
      setNowClock(formatISTClock());
    };
    tick();
    const id = setInterval(tick, 20000); // refresh every 20s so the minute stays accurate
    return () => clearInterval(id);
  }, []);

  const viewingNow = nowHour !== null && hour === nowHour;

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
          <Clock size={13} />
          {viewingNow ? (
            <>Now &middot; {nowClock || formatHour(hour)} IST</>
          ) : (
            <>
              Viewing &middot; {formatHour(hour)}
              {nowHour !== null && (
                <button
                  type="button"
                  onClick={() => selectHour(nowHour)}
                  className="ml-2 rounded-pill bg-canvas px-2 py-0.5 text-[11px] font-medium text-muted transition hover:text-ink"
                >
                  Jump to now &middot; {nowClock}
                </button>
              )}
            </>
          )}
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
          const isNow = b.hour === nowHour;
          const isSafest = safestHour === b.key;
          const isRiskiest = riskiestHour === b.key;
          const heightPct = 18 + (b.value / maxValue) * 82;
          // Theme-aware neutral tones via CSS vars; risk colors stay fixed.
          let color = "rgb(var(--muted) / 0.45)";
          if (route) {
            color = isSelected
              ? "rgb(var(--ink))"
              : isRiskiest
                ? "#E1483C"
                : isSafest
                  ? "#2FAE4E"
                  : "rgb(var(--muted) / 0.35)";
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
              {isNow && !isSelected && (
                <span className="absolute -bottom-1.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-ink" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
