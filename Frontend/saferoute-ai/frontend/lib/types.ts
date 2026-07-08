// Types mirror the backend's response shapes 1:1 -- every field here comes
// straight from safe_route_engine.py's own output objects. Nothing here is
// invented; if a field isn't in the engine's JSON, it isn't in this file.

export type RouteMode = "fastest" | "safest" | "balanced" | "women_safety" | "emergency";

export interface StatusResponse {
  backend_connected: boolean;
  graph_loaded: boolean;
  routing_engine_ready: boolean;
  risk_engine_ready: boolean;
  node_count?: number;
  edge_count?: number;
  area_count?: number;
}

export interface AreasResponse {
  areas: string[];
}

export interface RoutePoint {
  area: string | null;
  lat: number;
  lng: number;
}

export interface RouteData {
  mode: RouteMode;
  hour: number;
  path_nodes: number[];
  path_edges: number[];
  coordinates: [number, number][];
  distance_m: number;
  travel_time_s: number;
  risk_score: number;
  estimated_duration_s: number;
  execution_time_ms: number;
  incidents_applied: boolean;
  incident_avoided: boolean;
  closed_edges_applied: boolean;
}

export interface RouteSummary {
  mode: RouteMode;
  hour: number;
  distance_m: number;
  travel_time_s: number;
  risk_score: number;
  estimated_duration_s: number;
  execution_time_ms: number;
  node_count: number;
}

export interface RouteExplanation {
  mode: RouteMode;
  distance_m: number;
  travel_time_s: number;
  risk_score: number;
  avg_lighting: number;
  avg_crime: number;
  avg_congestion: number;
  safe_havens_passed: number;
  incident_avoidance: boolean;
  reason: string;
}

export interface PredictiveRisk {
  mode: RouteMode;
  hourly_risk: Record<string, number>;
  safest_hour: string | null;
  riskiest_hour: string | null;
}

export interface SafeHaven {
  node: number;
  lat: number;
  lng: number;
  type: string;
  straight_line_distance_m?: number;
}

export interface EmergencyRoute {
  error?: string;
  sos_from: [number, number];
  snapped_node_distance_m: number;
  nearest_safe_havens: SafeHaven[];
  selected_haven: SafeHaven;
  route: RouteData;
  explanation: RouteExplanation;
}

export interface Incident {
  lat: number;
  lng: number;
  radius_m: number;
  severity: number;
}

// One document from the MongoDB risk-factor collection (per-location scores).
// Only the fields the UI reads are typed; the rest pass through via the index
// signature so nothing is lost.
export interface RiskFactor {
  _id: string;
  zone?: string | null;
  source_area?: string | null;
  destination_area?: string | null;
  road_name?: string | null;
  lat: number;
  lng: number;
  crime_score?: number;
  lighting_score?: number;
  road_risk_score?: number;
  time_risk?: number;
  [key: string]: unknown;
}

export interface RiskFactorsResponse {
  count: number;
  total: number;
  risk_factors: RiskFactor[];
}

export interface RouteResponse {
  source: RoutePoint;
  dest: RoutePoint;
  route: RouteData;
  summary: RouteSummary;
  explanation: RouteExplanation;
  predictive_risk: PredictiveRisk;
  emergency: EmergencyRoute | null;
  time_machine: unknown;
  incidents: Incident[];
  safe_havens_on_route: SafeHaven[];
  output_dir: string | null;
}
