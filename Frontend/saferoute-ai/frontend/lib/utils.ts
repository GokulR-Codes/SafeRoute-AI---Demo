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
  return getISTHour() === hour;
}

// --- IST (Asia/Kolkata) clock ---------------------------------------------
// The engine's risk model is defined in Indian Standard Time, so "now" must be
// IST regardless of the browser's own timezone. We derive it from Intl rather
// than a hardcoded +5:30 offset so it stays correct without DST assumptions.

const IST_TZ = "Asia/Kolkata";

export function getISTParts(): { hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: IST_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? "0");
  return { hour: get("hour") % 24, minute: get("minute") };
}

export function getISTHour(): number {
  return getISTParts().hour;
}

/** e.g. "10:42 AM" in IST, minute-accurate. */
export function formatISTClock(): string {
  const { hour, minute } = getISTParts();
  const period = hour < 12 ? "AM" : "PM";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}:${String(minute).padStart(2, "0")} ${period}`;
}

// --- Turn-by-turn steps derived from the route geometry --------------------
// The backend has no navigation engine, so these instructions are computed
// purely from the coordinate polyline the engine returns (bearing changes and
// haversine segment lengths). They describe the drawn route, nothing more.

export type NavTurn =
  | "start"
  | "straight"
  | "slight-left"
  | "slight-right"
  | "left"
  | "right"
  | "sharp-left"
  | "sharp-right"
  | "finish";

export interface NavStep {
  turn: NavTurn;
  instruction: string;
  distance_m: number;
}

function toRad(d: number): number {
  return (d * Math.PI) / 180;
}

function haversine(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const dLat = toRad(b[0] - a[0]);
  const dLng = toRad(b[1] - a[1]);
  const lat1 = toRad(a[0]);
  const lat2 = toRad(b[0]);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Compass bearing 0-360 from point a to point b. */
function bearing(a: [number, number], b: [number, number]): number {
  const lat1 = toRad(a[0]);
  const lat2 = toRad(b[0]);
  const dLng = toRad(b[1] - a[1]);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return (Math.atan2(y, x) * 180) / Math.PI;
}

function compass(deg: number): string {
  const dirs = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
  return dirs[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}

function classifyTurn(delta: number): NavTurn {
  const a = ((delta + 540) % 360) - 180; // normalize to [-180, 180]
  const mag = Math.abs(a);
  if (mag < 18) return "straight";
  const side = a < 0 ? "left" : "right";
  if (mag < 45) return (`slight-${side}`) as NavTurn;
  if (mag < 120) return side as NavTurn;
  return (`sharp-${side}`) as NavTurn;
}

const TURN_VERB: Record<NavTurn, string> = {
  start: "Head",
  straight: "Continue straight",
  "slight-left": "Bear left",
  "slight-right": "Bear right",
  left: "Turn left",
  right: "Turn right",
  "sharp-left": "Sharp left",
  "sharp-right": "Sharp right",
  finish: "Arrive at destination",
};

export function buildNavSteps(
  coords: [number, number][],
  destLabel?: string | null
): NavStep[] {
  if (coords.length < 2) return [];

  // Segment bearings and lengths between consecutive vertices.
  const segBearing: number[] = [];
  const segLen: number[] = [];
  for (let i = 0; i < coords.length - 1; i++) {
    segBearing.push(bearing(coords[i], coords[i + 1]));
    segLen.push(haversine(coords[i], coords[i + 1]));
  }

  const steps: NavStep[] = [];
  // First step: head in the initial direction.
  let acc = segLen[0];
  steps.push({
    turn: "start",
    instruction: `Head ${compass(segBearing[0])}`,
    distance_m: acc,
  });

  // Interior vertices: emit a step only where the direction changes enough.
  for (let i = 1; i < segBearing.length; i++) {
    const turn = classifyTurn(segBearing[i] - segBearing[i - 1]);
    if (turn === "straight") {
      acc += segLen[i];
      steps[steps.length - 1].distance_m = acc;
      continue;
    }
    acc = segLen[i];
    steps.push({ turn, instruction: TURN_VERB[turn], distance_m: acc });
  }

  steps.push({
    turn: "finish",
    instruction: destLabel ? `Arrive at ${destLabel}` : "Arrive at destination",
    distance_m: 0,
  });
  return steps;
}
