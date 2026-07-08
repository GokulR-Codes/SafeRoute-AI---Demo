"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import TopBar from "@/components/TopBar";
import ThemeToggle from "@/components/ThemeToggle";
import RiskLayerToggle from "@/components/RiskLayerToggle";
import RoutePlanner from "@/components/RoutePlanner";
import RouteDetailsCard from "@/components/RouteDetailsCard";
import NavigationPanel from "@/components/NavigationPanel";
import RiskTimeline from "@/components/RiskTimeline";
import SosButton from "@/components/SosButton";
import { useSafeRouteStore } from "@/lib/store";
import { fetchAreas, fetchStatus } from "@/lib/api";

// Leaflet touches `window` at import time, so the map can only render
// client-side -- ssr: false keeps it out of the server bundle entirely.
const Map = dynamic(() => import("@/components/Map"), { ssr: false });

export default function Home() {
  const setStatus = useSafeRouteStore((s) => s.setStatus);
  const setAreas = useSafeRouteStore((s) => s.setAreas);
  const setError = useSafeRouteStore((s) => s.setError);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const status = await fetchStatus();
        if (cancelled) return;
        setStatus(status);
        if (status.graph_loaded) {
          const areas = await fetchAreas();
          if (!cancelled) setAreas(areas);
        }
      } catch {
        if (!cancelled) {
          setError("Can't reach the backend. Make sure it's running on http://localhost:8000.");
        }
      }
    }

    bootstrap();
    const interval = setInterval(bootstrap, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [setStatus, setAreas, setError]);

  return (
    <main className="app-shell relative w-screen overflow-hidden bg-canvas">
      <div className="absolute inset-0 z-0">
        <Map />
      </div>

      <div className="pointer-events-none absolute inset-0 z-[500] flex flex-col gap-3 p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="pointer-events-none w-full max-w-sm">
            <TopBar />
          </div>
          <div className="flex items-start gap-2">
            <RiskLayerToggle />
            <ThemeToggle />
          </div>
        </div>

        <div className="flex flex-1 items-start justify-between gap-4">
          <div className="pointer-events-none">
            <RoutePlanner />
          </div>
          <div className="pointer-events-none hidden max-h-[calc(100vh-8rem)] md:block">
            <RouteDetailsCard />
            <NavigationPanel />
          </div>
        </div>

        <div className="flex items-end justify-between gap-4">
          <div className="pointer-events-none block md:hidden">
            <RouteDetailsCard />
            <NavigationPanel />
          </div>
          <div className="pointer-events-none flex-1">
            <RiskTimeline />
          </div>
          <SosButton />
        </div>
      </div>
    </main>
  );
}
