"use client";

import { useMemo } from "react";
import {
  ArrowUp,
  ArrowUpLeft,
  ArrowUpRight,
  CornerUpLeft,
  CornerUpRight,
  MapPin,
  Flag,
  X,
  ShieldCheck,
} from "lucide-react";
import { useSafeRouteStore } from "@/lib/store";
import {
  buildNavSteps,
  formatDistance,
  formatDuration,
  riskLabel,
  riskLevel,
  type NavTurn,
} from "@/lib/utils";

const RISK_STYLES: Record<string, string> = {
  low: "bg-risk-lowBg text-risk-low",
  moderate: "bg-risk-moderateBg text-risk-moderate",
  high: "bg-risk-highBg text-risk-high",
};

const TURN_ICON: Record<NavTurn, React.ElementType> = {
  start: MapPin,
  straight: ArrowUp,
  "slight-left": ArrowUpLeft,
  "slight-right": ArrowUpRight,
  left: CornerUpLeft,
  right: CornerUpRight,
  "sharp-left": CornerUpLeft,
  "sharp-right": CornerUpRight,
  finish: Flag,
};

export default function NavigationPanel() {
  const route = useSafeRouteStore((s) => s.route);
  const navigating = useSafeRouteStore((s) => s.navigating);
  const setNavigating = useSafeRouteStore((s) => s.setNavigating);

  const steps = useMemo(
    () => (route ? buildNavSteps(route.route.coordinates, route.dest.area) : []),
    [route]
  );

  if (!navigating || !route) return null;

  const { summary, explanation } = route;
  const level = riskLevel(summary.risk_score);

  return (
    <div className="pointer-events-auto flex max-h-full w-[340px] flex-col overflow-hidden rounded-card border border-line bg-surface/95 shadow-floating backdrop-blur">
      {/* Header: live route summary */}
      <div className="border-b border-line p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-semibold text-ink">
                {formatDuration(summary.estimated_duration_s)}
              </span>
              <span className="text-sm text-muted">{formatDistance(summary.distance_m)}</span>
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
              <span className="font-medium text-source">{route.source.area ?? "Start"}</span>
              <span aria-hidden>&rarr;</span>
              <span className="font-medium text-danger">{route.dest.area ?? "Destination"}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => setNavigating(false)}
            aria-label="End navigation"
            className="rounded-full p-1.5 text-muted transition hover:bg-canvas hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <span className={`rounded-pill px-2.5 py-1 text-xs font-semibold ${RISK_STYLES[level]}`}>
            {riskLabel(summary.risk_score)}
          </span>
          {explanation.safe_havens_passed > 0 && (
            <span className="flex items-center gap-1 rounded-pill bg-risk-lowBg px-2.5 py-1 text-xs font-semibold text-risk-low">
              <ShieldCheck size={13} />
              {explanation.safe_havens_passed} safe haven
              {explanation.safe_havens_passed > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Turn-by-turn list */}
      <ol className="flex-1 overflow-y-auto p-2">
        {steps.map((step, i) => {
          const Icon = TURN_ICON[step.turn];
          const isEnd = step.turn === "finish";
          return (
            <li
              key={i}
              className="flex items-center gap-3 rounded-xl px-2 py-2.5 transition hover:bg-canvas"
            >
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                  isEnd ? "bg-danger text-white" : "bg-canvas text-ink"
                }`}
              >
                <Icon size={17} />
              </span>
              <span className="flex-1 text-sm text-ink">{step.instruction}</span>
              {step.distance_m > 0 && (
                <span className="shrink-0 text-xs tabular-nums text-muted">
                  {formatDistance(step.distance_m)}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      <div className="border-t border-line p-3">
        <button
          type="button"
          onClick={() => setNavigating(false)}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-line py-2.5 text-sm font-semibold text-ink transition hover:bg-canvas"
        >
          End navigation
        </button>
        <p className="mt-2 text-center text-[10px] text-muted">
          Directions are derived from the route path, not live GPS.
        </p>
      </div>
    </div>
  );
}
