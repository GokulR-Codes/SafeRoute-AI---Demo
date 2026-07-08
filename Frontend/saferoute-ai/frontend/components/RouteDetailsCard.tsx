"use client";

import { Lightbulb, ShieldAlert, Building2, Navigation } from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import { formatDistance, formatDuration, riskLabel, riskLevel } from "@/lib/utils";

const RISK_STYLES: Record<string, string> = {
  low: "bg-risk-lowBg text-risk-low",
  moderate: "bg-risk-moderateBg text-risk-moderate",
  high: "bg-risk-highBg text-risk-high",
};

export default function RouteDetailsCard() {
  const route = useSafeRouteStore((s) => s.route);
  const loading = useSafeRouteStore((s) => s.loading);
  const error = useSafeRouteStore((s) => s.error);
  const navigating = useSafeRouteStore((s) => s.navigating);
  const setNavigating = useSafeRouteStore((s) => s.setNavigating);

  // While navigating, NavigationPanel takes over this slot.
  if (navigating) return null;

  if (error) {
    return (
      <div className="pointer-events-auto w-[320px] rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
        <p className="text-sm font-medium text-danger">{error}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="pointer-events-auto w-[320px] animate-pulse rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
        <div className="h-5 w-32 rounded bg-line" />
        <div className="mt-3 h-4 w-full rounded bg-line" />
        <div className="mt-2 h-4 w-2/3 rounded bg-line" />
      </div>
    );
  }

  if (!route) {
    return (
      <div className="pointer-events-auto w-[320px] rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
        <p className="text-sm text-muted">
          Choose a source and destination, then generate a route to see details here.
        </p>
      </div>
    );
  }

  const { summary, explanation } = route;
  const level = riskLevel(summary.risk_score);

  return (
    <div className="pointer-events-auto w-[320px] rounded-card border border-line bg-surface/95 p-4 shadow-floating backdrop-blur">
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-3xl font-semibold text-ink">
            {formatDuration(summary.estimated_duration_s)}
          </span>
          <span className="text-sm text-muted">{formatDistance(summary.distance_m)}</span>
        </div>
        <span className={`rounded-pill px-2.5 py-1 text-xs font-semibold ${RISK_STYLES[level]}`}>
          {riskLabel(summary.risk_score)}
        </span>
      </div>

      <p className="mt-1.5 text-sm text-muted">{explanation.reason}</p>

      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-3">
        <Stat icon={Lightbulb} label="Lighting" value={explanation.avg_lighting.toFixed(2)} />
        <Stat icon={ShieldAlert} label="Crime score" value={explanation.avg_crime.toFixed(2)} />
        <Stat icon={Building2} label="Safe havens" value={String(explanation.safe_havens_passed)} />
      </div>

      <button
        type="button"
        onClick={() => setNavigating(true)}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-2.5 text-sm font-semibold text-surface transition hover:opacity-90"
      >
        <Navigation size={15} />
        Start navigation
      </button>
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-1 text-center">
      <Icon size={16} className="text-muted" />
      <span className="font-display text-sm font-semibold text-ink">{value}</span>
      <span className="text-[10px] uppercase tracking-wide text-muted">{label}</span>
    </div>
  );
}
