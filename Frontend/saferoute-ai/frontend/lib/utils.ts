export function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 1) return "<1 min";
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

export type RiskLevel = "low" | "moderate" | "high";

export function riskLevel(score: number): RiskLevel {
  if (score < 0.25) return "low";
  if (score < 0.5) return "moderate";
  return "high";
}

export function riskLabel(score: number): string {
  const level = riskLevel(score);
  return level === "low" ? "Low risk" : level === "moderate" ? "Moderate risk" : "High risk";
}

export function formatHour(hour: number): string {
  const h = ((hour % 24) + 24) % 24;
  const period = h < 12 ? "AM" : "PM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display} ${period}`;
}

export function isNowHour(hour: number): boolean {
  return new Date().getHours() === hour;
}
