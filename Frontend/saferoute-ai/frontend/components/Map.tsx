"use client";

import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, useMap } from "react-leaflet";
import type { LatLngExpression, LatLngBoundsExpression } from "leaflet";
import { useSafeRouteStore } from "@/lib/store";

const DEFAULT_CENTER: LatLngExpression = [12.9716, 77.5946]; // Bengaluru fallback
const DEFAULT_ZOOM = 13;

function FitToRoute({ coordinates }: { coordinates: [number, number][] }) {
  const map = useMap();

  useEffect(() => {
    if (!coordinates.length) return;
    if (coordinates.length === 1) {
      map.setView(coordinates[0], 16, { animate: true });
      return;
    }
    const bounds = coordinates as LatLngBoundsExpression;
    map.fitBounds(bounds, { padding: [80, 80] });
  }, [coordinates, map]);

  return null;
}

export default function Map() {
  const route = useSafeRouteStore((s) => s.route);
  const mapRef = useRef(null);

  const coordinates = useMemo<[number, number][]>(
    () => route?.route.coordinates ?? [],
    [route]
  );

  const sourcePos = route ? ([route.source.lat, route.source.lng] as LatLngExpression) : null;
  const destPos = route ? ([route.dest.lat, route.dest.lng] as LatLngExpression) : null;

  return (
    <MapContainer
      ref={mapRef}
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      zoomControl={false}
      className="h-full w-full"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {coordinates.length > 1 && (
        <>
          <Polyline
            positions={coordinates}
            pathOptions={{ color: "#2FAE4E", weight: 5, opacity: 0.95, lineCap: "round" }}
          />
          <FitToRoute coordinates={coordinates} />
        </>
      )}

      {sourcePos && (
        <CircleMarker
          center={sourcePos}
          radius={8}
          pathOptions={{ color: "#2F6FED", fillColor: "#2F6FED", fillOpacity: 1, weight: 3 }}
        >
          <Tooltip permanent direction="top" offset={[0, -10]} className="!rounded-full !border-none !bg-ink !text-white !text-xs !px-2 !py-1">
            {route?.source.area ?? "Start"}
          </Tooltip>
        </CircleMarker>
      )}

      {destPos && (
        <CircleMarker
          center={destPos}
          radius={9}
          pathOptions={{ color: "#E1483C", fillColor: "#E1483C", fillOpacity: 1, weight: 3 }}
        >
          <Tooltip permanent direction="top" offset={[0, -10]} className="!rounded-full !border-none !bg-ink !text-white !text-xs !px-2 !py-1">
            {route?.dest.area ?? "Destination"}
          </Tooltip>
        </CircleMarker>
      )}

      {route?.safe_havens_on_route.map((h) => (
        <CircleMarker
          key={h.node}
          center={[h.lat, h.lng] as LatLngExpression}
          radius={6}
          pathOptions={{ color: "#2FAE4E", fillColor: "#FFFFFF", fillOpacity: 1, weight: 3 }}
        >
          <Tooltip direction="top" offset={[0, -8]} className="!rounded-lg !text-xs">
            {h.type === "unspecified" ? "Safe haven" : h.type}
          </Tooltip>
        </CircleMarker>
      ))}

      {route?.incidents.map((inc, i) => (
        <CircleMarker
          key={i}
          center={[inc.lat, inc.lng] as LatLngExpression}
          radius={7}
          pathOptions={{ color: "#D98A16", fillColor: "#D98A16", fillOpacity: 0.35, weight: 2 }}
        >
          <Tooltip direction="top" offset={[0, -8]} className="!rounded-lg !text-xs">
            Incident nearby
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
