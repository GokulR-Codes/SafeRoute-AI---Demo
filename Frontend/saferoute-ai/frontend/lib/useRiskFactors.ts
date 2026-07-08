"use client";

import { useEffect, useState } from "react";
import { fetchRiskFactors } from "./api";
import type { RiskFactor } from "./types";

// Module-level cache so toggling the layer off/on (or remounting the map)
// doesn't refetch the few-thousand-doc collection every time.
let cache: RiskFactor[] | null = null;

interface UseRiskFactors {
  data: RiskFactor[] | null;
  loading: boolean;
  error: string | null;
}

/**
 * Lazily loads the risk-factor collection the first time `enabled` is true,
 * then serves it from an in-memory cache. Returns nothing until enabled.
 */
export function useRiskFactors(enabled: boolean): UseRiskFactors {
  const [data, setData] = useState<RiskFactor[] | null>(cache);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || cache) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchRiskFactors()
      .then((docs) => {
        cache = docs;
        if (!cancelled) setData(docs);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? "Couldn't load risk factors.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { data, loading, error };
}
