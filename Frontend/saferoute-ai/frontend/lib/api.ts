import axios from "axios";
import type {
  AreasResponse,
  RiskFactor,
  RiskFactorsResponse,
  RouteMode,
  RouteResponse,
  StatusResponse,
} from "./types";

// The backend is the small FastAPI wrapper in /backend that imports
// safe_route_engine.py in-process. Override with NEXT_PUBLIC_API_BASE if
// it's running somewhere other than localhost:8000.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const client = axios.create({ baseURL: API_BASE, timeout: 15000 });

export async function fetchStatus(): Promise<StatusResponse> {
  const { data } = await client.get<StatusResponse>("/api/status");
  return data;
}

export async function fetchAreas(): Promise<string[]> {
  const { data } = await client.get<AreasResponse>("/api/areas");
  return data.areas;
}

export interface GenerateRouteParams {
  sourceArea: string;
  destArea: string;
  mode: RouteMode;
  hour: number;
}

export async function generateRoute(params: GenerateRouteParams): Promise<RouteResponse> {
  const { data } = await client.post<RouteResponse>("/api/route", {
    source_area: params.sourceArea,
    dest_area: params.destArea,
    mode: params.mode,
    hour: params.hour,
  });
  return data;
}

export interface RiskFactorParams {
  zone?: string;
  sourceArea?: string;
  limit?: number;
}

export async function fetchRiskFactors(params?: RiskFactorParams): Promise<RiskFactor[]> {
  const { data } = await client.get<RiskFactorsResponse>("/api/risk-factors", {
    params: {
      zone: params?.zone,
      source_area: params?.sourceArea,
      limit: params?.limit,
    },
    timeout: 30000, // the full collection is a few thousand docs
  });
  return data.risk_factors;
}

export async function triggerSos(lat: number, lng: number, hour: number) {
  const { data } = await client.post("/api/sos", { slat: lat, slng: lng, hour });
  return data;
}
