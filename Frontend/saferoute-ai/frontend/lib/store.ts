import { create } from "zustand";
import type { RouteMode, RouteResponse, StatusResponse } from "./types";

interface SafeRouteState {
  status: StatusResponse | null;
  areas: string[];
  sourceArea: string | null;
  destArea: string | null;
  mode: RouteMode;
  hour: number;
  loading: boolean;
  error: string | null;
  route: RouteResponse | null;

  setStatus: (s: StatusResponse) => void;
  setAreas: (a: string[]) => void;
  setSourceArea: (a: string | null) => void;
  setDestArea: (a: string | null) => void;
  swapAreas: () => void;
  setMode: (m: RouteMode) => void;
  setHour: (h: number) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  setRoute: (r: RouteResponse | null) => void;
}

export const useSafeRouteStore = create<SafeRouteState>((set, get) => ({
  status: null,
  areas: [],
  sourceArea: null,
  destArea: null,
  mode: "balanced",
  hour: new Date().getHours(),
  loading: false,
  error: null,
  route: null,

  setStatus: (s) => set({ status: s }),
  setAreas: (a) => set({ areas: a }),
  setSourceArea: (a) => set({ sourceArea: a }),
  setDestArea: (a) => set({ destArea: a }),
  swapAreas: () => set({ sourceArea: get().destArea, destArea: get().sourceArea }),
  setMode: (m) => set({ mode: m }),
  setHour: (h) => set({ hour: h }),
  setLoading: (v) => set({ loading: v }),
  setError: (e) => set({ error: e }),
  setRoute: (r) => set({ route: r }),
}));
