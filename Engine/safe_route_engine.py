"""
SafeRoute-AI v8 - Ultra-Lightweight Routing Engine
====================================================
Loads a pre-generated graph (nodes, edges, hourly edge weights) once and
serves millisecond-latency A* routing with dynamic, time-of-day, risk-aware
edge costs. No graph regeneration, no heavy GIS stack.

Input files (fixed schema, already generated upstream):
    graph_nodes.csv          node_id, lat, lng, degree, is_safe_haven,
                              static_component, graph_component
    graph_edges.csv          edge_id, u, v, edge_length_m, estimated_travel_time,
                              speed_limit, lighting_score, crime_score,
                              isolated_area_score, road_risk_score, flood_risk,
                              cctv_density_estimate, police_station_distance,
                              congestion_score, time_risk, road_type, zone_type, ...
    hourly_edge_weights.csv  edge_id, hour_00 ... hour_23  (time-of-day risk factor, 0-1)

Optional:
    incident_layer.csv       lat, lng, radius_m, severity   (live incidents)
    safe_havens.csv          lat, lng, type                 (hospitals/police/etc.)

Usage:
    python safe_route_engine.py --slat 12.9750 --slng 77.6400 \
                                 --elat 12.9680 --elng 77.6420 \
                                 --mode balanced --hour 20
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

DEFAULT_DATA_DIR = r"D:\Project\SafeRoute - Demo\Datasets\Edges - Weights"
DATA_DIR = Path(os.environ.get("SAFEROUTE_DATA_DIR", DEFAULT_DATA_DIR))

NODES_FILE = "graph_nodes.csv"
EDGES_FILE = "graph_edges.csv"
HOURLY_FILE = "hourly_edge_weights.csv"
INCIDENTS_FILE = "incident_layer.csv"
SAFE_HAVENS_FILE = "safe_havens.csv"

EARTH_RADIUS_M = 6371000.0
NUM_HOURS = 24

# Per-mode risk factor weights. Every factor is a normalized 0-1 "badness"
# score. `risk_scale` controls how strongly the blended risk inflates the
# base travel-time cost of an edge: cost = time * (1 + risk_scale * risk).
MODE_PROFILES: Dict[str, Dict[str, float]] = {
    "fastest": {
        "crime": 0.00, "lighting": 0.00, "isolation": 0.00, "road_risk": 0.05,
        "flood": 0.10, "cctv": 0.00, "police_dist": 0.00, "time_risk": 0.00,
        "dynamic": 0.20, "risk_scale": 0.35,
    },
    "safest": {
        "crime": 0.95, "lighting": 0.95, "isolation": 0.85, "road_risk": 0.70,
        "flood": 0.65, "cctv": 0.55, "police_dist": 0.45, "time_risk": 0.55,
        "dynamic": 0.90, "risk_scale": 3.20,
    },
    "balanced": {
        "crime": 0.55, "lighting": 0.55, "isolation": 0.45, "road_risk": 0.40,
        "flood": 0.35, "cctv": 0.25, "police_dist": 0.25, "time_risk": 0.35,
        "dynamic": 0.55, "risk_scale": 1.30,
    },
    "women_safety": {
        "crime": 1.00, "lighting": 1.00, "isolation": 0.90, "road_risk": 0.45,
        "flood": 0.25, "cctv": 0.85, "police_dist": 0.75, "time_risk": 0.60,
        "dynamic": 1.00, "risk_scale": 3.75,
    },
    "emergency": {
        "crime": 0.10, "lighting": 0.10, "isolation": 0.10, "road_risk": 0.35,
        "flood": 0.45, "cctv": 0.00, "police_dist": 0.00, "time_risk": 0.10,
        "dynamic": 0.20, "risk_scale": 0.55,
    },
}

FACTOR_KEYS = ["crime", "lighting", "isolation", "road_risk", "flood",
               "cctv", "police_dist", "time_risk", "dynamic"]


# --------------------------------------------------------------------------
# HAVERSINE
# --------------------------------------------------------------------------

def haversine_scalar(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def haversine_vec(lat1, lng1, lat2, lng2):
    """Vectorized haversine distance (numpy arrays or scalars) in meters."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(a)))


# --------------------------------------------------------------------------
# GRAPH LOADING
# --------------------------------------------------------------------------

def _clip01(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr, 0.0, 1.0)


def _union_find_components(num_nodes: int, edges_u: np.ndarray, edges_v: np.ndarray) -> Tuple[int, np.ndarray]:
    """Connected component count via union-find (no networkx)."""
    parent = np.arange(num_nodes)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for u, v in zip(edges_u, edges_v):
        ru, rv = find(int(u)), find(int(v))
        if ru != rv:
            parent[ru] = rv

    for i in range(num_nodes):
        parent[i] = find(i)

    comp_ids = parent
    num_components = len(np.unique(comp_ids))
    return num_components, comp_ids


def load_graph(data_dir: Optional[Path] = None) -> Dict:
    """Load nodes/edges/hourly weights once and build in-memory routing
    structures (adjacency list, KD-tree, risk factor arrays). This is the
    only place CSVs are parsed."""
    t0 = time.perf_counter()
    data_dir = Path(data_dir) if data_dir else DATA_DIR

    nodes_path = data_dir / NODES_FILE
    edges_path = data_dir / EDGES_FILE
    hourly_path = data_dir / HOURLY_FILE

    for p in (nodes_path, edges_path, hourly_path):
        if not p.exists():
            raise FileNotFoundError(f"Required input file missing: {p}")

    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)
    hourly_df = pd.read_csv(hourly_path)

    # --- node id -> contiguous index map (defensive; usually already 0..N-1) ---
    node_ids = nodes_df["node_id"].to_numpy()
    id_to_index = {int(nid): i for i, nid in enumerate(node_ids)}
    num_nodes = len(nodes_df)

    lat = nodes_df["lat"].to_numpy(dtype=np.float64)
    lng = nodes_df["lng"].to_numpy(dtype=np.float64)
    is_safe_haven = nodes_df["is_safe_haven"].to_numpy(dtype=np.int8) if "is_safe_haven" in nodes_df else np.zeros(num_nodes, dtype=np.int8)

    if np.isnan(lat).any() or np.isnan(lng).any():
        raise ValueError("Validation failed: missing node coordinates.")

    # --- edges, remapped through id_to_index defensively ---
    num_edges = len(edges_df)
    edge_u = edges_df["u"].map(id_to_index).to_numpy()
    edge_v = edges_df["v"].map(id_to_index).to_numpy()
    if np.isnan(edge_u.astype(float)).any() or np.isnan(edge_v.astype(float)).any():
        raise ValueError("Validation failed: edge references a node_id not present in graph_nodes.csv")
    edge_u = edge_u.astype(np.int32)
    edge_v = edge_v.astype(np.int32)

    edge_length_m = edges_df["edge_length_m"].to_numpy(dtype=np.float64)
    edge_time_s = edges_df["estimated_travel_time"].to_numpy(dtype=np.float64)
    speed_limit = edges_df["speed_limit"].to_numpy(dtype=np.float64)
    road_type = edges_df["road_type"].astype(str).to_numpy()
    zone_type = edges_df["zone_type"].astype(str).to_numpy() if "zone_type" in edges_df else np.array(["Unknown"] * num_edges)

    # risk factor arrays (0-1 "badness"; lighting/cctv are inverted so higher = worse)
    risk_crime = _clip01(edges_df["crime_score"].to_numpy(dtype=np.float64))
    risk_lighting = _clip01(1.0 - edges_df["lighting_score"].to_numpy(dtype=np.float64))
    risk_isolation = _clip01(edges_df["isolated_area_score"].to_numpy(dtype=np.float64))
    risk_road = _clip01(edges_df["road_risk_score"].to_numpy(dtype=np.float64))
    risk_flood = _clip01(edges_df["flood_risk"].to_numpy(dtype=np.float64))
    risk_cctv = _clip01(1.0 - edges_df["cctv_density_estimate"].to_numpy(dtype=np.float64))
    risk_police = _clip01(edges_df["police_station_distance"].to_numpy(dtype=np.float64))
    risk_timebase = _clip01(edges_df["time_risk"].to_numpy(dtype=np.float64)) if "time_risk" in edges_df else np.zeros(num_edges)
    congestion_static = _clip01(edges_df["congestion_score"].to_numpy(dtype=np.float64)) if "congestion_score" in edges_df else np.zeros(num_edges)

    lighting_raw = edges_df["lighting_score"].to_numpy(dtype=np.float64)
    crime_raw = edges_df["crime_score"].to_numpy(dtype=np.float64)

    # --- hourly dynamic weights, aligned to edge_id order ---
    hour_cols = [f"hour_{h:02d}" for h in range(NUM_HOURS)]
    missing_hours = [c for c in hour_cols if c not in hourly_df.columns]
    if missing_hours:
        raise ValueError(f"Validation failed: hourly_edge_weights.csv missing columns {missing_hours}")
    hourly_indexed = hourly_df.set_index("edge_id").reindex(edges_df["edge_id"])
    if hourly_indexed[hour_cols].isna().any().any():
        raise ValueError("Validation failed: hourly weights missing for one or more edge_id values.")
    hourly_matrix = _clip01(hourly_indexed[hour_cols].to_numpy(dtype=np.float64))  # (num_edges, 24)

    # --- global max speed limit -> admissible A* heuristic denominator ---
    v_max_mps = float(np.max(speed_limit)) / 3.6
    v_max_mps = max(v_max_mps, 1.0)

    # --- adjacency list (bidirectional): node_index -> list[(neighbor_index, edge_index)] ---
    adjacency: List[List[Tuple[int, int]]] = [[] for _ in range(num_nodes)]
    for e in range(num_edges):
        u, v = int(edge_u[e]), int(edge_v[e])
        adjacency[u].append((v, e))
        adjacency[v].append((u, e))

    degree = np.array([len(a) for a in adjacency], dtype=np.int32)

    # --- connectivity validation ---
    num_components, component_ids = _union_find_components(num_nodes, edge_u, edge_v)

    # --- KD-tree over an equirectangular local projection (meters) ---
    t_kd0 = time.perf_counter()
    lat0 = float(np.mean(lat))
    proj_x = EARTH_RADIUS_M * np.radians(lng) * math.cos(math.radians(lat0))
    proj_y = EARTH_RADIUS_M * np.radians(lat)
    kdtree = cKDTree(np.column_stack([proj_x, proj_y]))
    kdtree_build_time = time.perf_counter() - t_kd0

    # --- safe havens ---
    safe_haven_indices = np.where(is_safe_haven == 1)[0].tolist()
    safe_haven_types = {int(i): "unspecified" for i in safe_haven_indices}
    safe_haven_path = data_dir / SAFE_HAVENS_FILE
    if safe_haven_path.exists():
        havens_df = pd.read_csv(safe_haven_path)
        h_x = EARTH_RADIUS_M * np.radians(havens_df["lng"].to_numpy(dtype=np.float64)) * math.cos(math.radians(lat0))
        h_y = EARTH_RADIUS_M * np.radians(havens_df["lat"].to_numpy(dtype=np.float64))
        _, nn_idx = kdtree.query(np.column_stack([h_x, h_y]))
        for row_i, node_idx in enumerate(nn_idx):
            node_idx = int(node_idx)
            haven_type = str(havens_df["type"].iloc[row_i]) if "type" in havens_df.columns else "unspecified"
            safe_haven_types[node_idx] = haven_type
            if node_idx not in safe_haven_indices:
                safe_haven_indices.append(node_idx)

    safe_haven_kdtree = None
    if safe_haven_indices:
        sh_arr = np.array(safe_haven_indices, dtype=np.int32)
        safe_haven_kdtree = cKDTree(np.column_stack([proj_x[sh_arr], proj_y[sh_arr]]))

    # --- optional default incidents loaded at startup (also settable per-request) ---
    default_incidents = []
    incidents_path = data_dir / INCIDENTS_FILE
    if incidents_path.exists():
        inc_df = pd.read_csv(incidents_path)
        for _, row in inc_df.iterrows():
            default_incidents.append({
                "lat": float(row["lat"]), "lng": float(row["lng"]),
                "radius_m": float(row.get("radius_m", row.get("radius", 200.0))),
                "severity": float(row.get("severity", 0.5)),
            })

    load_time = time.perf_counter() - t0
    process = None
    try:
        mem_bytes = sum(a.nbytes for a in [
            lat, lng, edge_u, edge_v, edge_length_m, edge_time_s, speed_limit,
            risk_crime, risk_lighting, risk_isolation, risk_road, risk_flood,
            risk_cctv, risk_police, risk_timebase, congestion_static, hourly_matrix,
            proj_x, proj_y,
        ])
    except Exception:
        mem_bytes = 0

    graph = {
        "data_dir": str(data_dir),
        "num_nodes": num_nodes, "num_edges": num_edges,
        "node_ids": node_ids, "id_to_index": id_to_index,
        "lat": lat, "lng": lng, "is_safe_haven": is_safe_haven,
        "edge_u": edge_u, "edge_v": edge_v,
        "edge_length_m": edge_length_m, "edge_time_s": edge_time_s,
        "speed_limit": speed_limit, "road_type": road_type, "zone_type": zone_type,
        "risk_crime": risk_crime, "risk_lighting": risk_lighting,
        "risk_isolation": risk_isolation, "risk_road": risk_road,
        "risk_flood": risk_flood, "risk_cctv": risk_cctv, "risk_police": risk_police,
        "risk_timebase": risk_timebase, "congestion_static": congestion_static,
        "lighting_raw": lighting_raw, "crime_raw": crime_raw,
        "hourly_matrix": hourly_matrix,
        "v_max_mps": v_max_mps,
        "adjacency": adjacency, "degree": degree,
        "num_components": num_components, "component_ids": component_ids,
        "kdtree": kdtree, "proj_x": proj_x, "proj_y": proj_y, "lat0": lat0,
        "safe_haven_indices": safe_haven_indices, "safe_haven_types": safe_haven_types,
        "safe_haven_kdtree": safe_haven_kdtree,
        "default_incidents": default_incidents,
        "load_time_s": load_time, "kdtree_build_time_s": kdtree_build_time,
        "mem_bytes": mem_bytes,
    }
    return graph


def validate_graph(graph: Dict) -> bool:
    """Startup validation. Aborts (raises) on failure, matching spec's
    'abort gracefully' requirement at the caller level."""
    checks = []
    checks.append(("Graph loaded", graph["num_nodes"] > 0 and graph["num_edges"] > 0))
    max_idx = graph["num_nodes"] - 1
    valid_refs = bool(np.all(graph["edge_u"] >= 0) and np.all(graph["edge_u"] <= max_idx)
                       and np.all(graph["edge_v"] >= 0) and np.all(graph["edge_v"] <= max_idx))
    checks.append(("Every edge references valid nodes", valid_refs))
    checks.append(("Hourly weights exist", graph["hourly_matrix"].shape == (graph["num_edges"], NUM_HOURS)))
    checks.append(("No missing coordinates", not (np.isnan(graph["lat"]).any() or np.isnan(graph["lng"]).any())))
    checks.append(("Connected graph", graph["num_components"] == 1))
    checks.append(("KDTree built", graph["kdtree"] is not None))

    ok = True
    for name, passed in checks:
        mark = "\u2713" if passed else "\u2717"
        print(f"{mark} {name}")
        if not passed:
            ok = False
    if not ok:
        raise RuntimeError("Graph validation failed. Aborting startup.")
    return True


def log_startup_summary(graph: Dict) -> None:
    avg_degree = float(np.mean(graph["degree"])) if graph["num_nodes"] else 0.0
    print(f"Nodes: {graph['num_nodes']}")
    print(f"Edges: {graph['num_edges']}")
    print(f"Average Degree: {avg_degree:.2f}")
    print(f"Connected Components: {graph['num_components']}")
    print(f"Graph Load Time: {graph['load_time_s'] * 1000:.2f} ms")
    print(f"KDTree Build Time: {graph['kdtree_build_time_s'] * 1000:.2f} ms")
    print(f"Memory Usage: {graph['mem_bytes'] / (1024 * 1024):.2f} MB")


# --------------------------------------------------------------------------
# NEAREST NODE SEARCH
# --------------------------------------------------------------------------

def nearest_node(graph: Dict, lat: float, lng: float) -> Tuple[int, float]:
    """Returns (node_index, distance_m) for the nearest graph node. O(log n)."""
    x = EARTH_RADIUS_M * math.radians(lng) * math.cos(math.radians(graph["lat0"]))
    y = EARTH_RADIUS_M * math.radians(lat)
    dist, idx = graph["kdtree"].query([x, y])
    return int(idx), float(dist)


# --------------------------------------------------------------------------
# DYNAMIC AREA DETECTION & RESOLUTION
# --------------------------------------------------------------------------
# Only these functions replace the old hardcoded-coordinate workflow.
# They read graph_edges.csv (already produced upstream) purely to discover
# area names and map them back to existing node_ids -- no graph reload, no
# KDTree rebuild, no change to graph topology or routing algorithms.

AREA_COLUMNS_PRIORITY = ["source_area", "destination_area", "road_name", "zone"]

_BAD_VALUES = {"", "nan", "none", "null", "0", "unknown"}


def _clean_area_value(val) -> Optional[str]:
    """Normalizes a raw cell value; returns None if it should be ignored."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in _BAD_VALUES:
        return None
    return s


def load_area_index(data_dir: Optional[Path] = None) -> Dict:
    """One-time scan of graph_edges.csv to build:
      - a sorted, deduplicated list of every usable area name
      - a map: area name -> set of node_ids referenced by matching edges
    graph_edges.csv is read once here; graph_nodes.csv / hourly weights /
    the routing graph itself are untouched."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    edges_path = data_dir / EDGES_FILE
    if not edges_path.exists():
        raise FileNotFoundError(f"Required input file missing: {edges_path}")

    edges_df = pd.read_csv(edges_path)
    present_cols = [c for c in AREA_COLUMNS_PRIORITY if c in edges_df.columns]
    if not present_cols:
        raise ValueError(
            "Validation failed: none of source_area/destination_area/road_name/zone "
            "found in graph_edges.csv"
        )

    areas_seen: List[str] = []
    areas_set = set()
    area_to_nodes: Dict[str, set] = defaultdict(set)

    has_u = "u" in edges_df.columns
    has_v = "v" in edges_df.columns
    u_col = edges_df["u"] if has_u else None
    v_col = edges_df["v"] if has_v else None

    for col in present_cols:
        col_values = edges_df[col]
        for row_i, raw_val in enumerate(col_values):
            cleaned = _clean_area_value(raw_val)
            if cleaned is None:
                continue
            if cleaned not in areas_set:
                areas_set.add(cleaned)
                areas_seen.append(cleaned)
            if has_u:
                area_to_nodes[cleaned].add(int(u_col.iloc[row_i]))
            if has_v:
                area_to_nodes[cleaned].add(int(v_col.iloc[row_i]))

    available_areas = sorted(areas_set)
    return {
        "available_areas": available_areas,
        "area_to_nodes": area_to_nodes,
    }


def resolve_area_to_node(graph: Dict, area_index: Dict, area_name: str) -> Tuple[int, float, float]:
    """Resolves an area name to a single graph node: centroid of every node
    tied to that area, snapped to the nearest existing graph node via the
    already-built KDTree (O(log n), never randomly chosen)."""
    node_ids = area_index["area_to_nodes"].get(area_name)
    if not node_ids:
        raise ValueError(f"Area '{area_name}' has no associated graph nodes.")

    id_to_index = graph["id_to_index"]
    indices = [id_to_index[nid] for nid in node_ids if nid in id_to_index]
    if not indices:
        raise ValueError(f"Area '{area_name}' node_ids not present in graph_nodes.csv.")

    centroid_lat = float(np.mean(graph["lat"][indices]))
    centroid_lng = float(np.mean(graph["lng"][indices]))

    node_idx, _snap_dist = nearest_node(graph, centroid_lat, centroid_lng)
    return node_idx, centroid_lat, centroid_lng


def prompt_select_area(available_areas: List[str], label: str) -> str:
    """STEP 3: accepts either the list-number or the exact area name.
    Redisplays the list on invalid input."""
    while True:
        print("\nAvailable Areas")
        for i, name in enumerate(available_areas, start=1):
            print(f"{i}. {name}")
        raw = input(f"\nSelect {label} (number or exact name): ").strip()

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(available_areas):
                return available_areas[idx - 1]
            print(f"Invalid number. Please choose between 1 and {len(available_areas)}.")
            continue

        if raw in available_areas:
            return raw

        matches = [a for a in available_areas if a.lower() == raw.lower()]
        if matches:
            return matches[0]

        print(f"'{raw}' is not a recognized area. Please try again.")


# --------------------------------------------------------------------------
# DYNAMIC EDGE COST MODEL
# --------------------------------------------------------------------------

def build_incident_multiplier(graph: Dict, incidents: Optional[List[Dict]]) -> Tuple[np.ndarray, np.ndarray]:
    """Temporary, in-memory-only edge cost multiplier from live incidents.
    Never mutates the base graph arrays. Returns (multiplier, affected_mask)."""
    mult = np.ones(graph["num_edges"], dtype=np.float64)
    affected_mask = np.zeros(graph["num_edges"], dtype=bool)
    if not incidents:
        return mult, affected_mask

    mid_lat = (graph["lat"][graph["edge_u"]] + graph["lat"][graph["edge_v"]]) / 2.0
    mid_lng = (graph["lng"][graph["edge_u"]] + graph["lng"][graph["edge_v"]]) / 2.0

    for inc in incidents:
        d = haversine_vec(mid_lat, mid_lng, inc["lat"], inc["lng"])
        radius = float(inc.get("radius_m", inc.get("radius", 200.0)))
        severity = float(inc.get("severity", 0.5))
        affected = d <= radius
        if np.any(affected):
            mult[affected] *= (1.0 + severity * 4.0)
            affected_mask |= affected
    return mult, affected_mask


def compute_edge_costs(
    graph: Dict,
    mode: str,
    hour: int,
    incident_multiplier: Optional[np.ndarray] = None,
    closed_edges: Optional[List[int]] = None,
) -> np.ndarray:
    """Vectorized per-request edge cost array (seconds). Computed fresh for
    every routing call; the underlying graph arrays are never modified."""
    profile = MODE_PROFILES.get(mode, MODE_PROFILES["balanced"])
    hour = int(hour) % NUM_HOURS
    dynamic = graph["hourly_matrix"][:, hour]

    weight_sum = sum(profile[k] for k in FACTOR_KEYS) or 1.0
    composite_risk = (
        profile["crime"] * graph["risk_crime"] +
        profile["lighting"] * graph["risk_lighting"] +
        profile["isolation"] * graph["risk_isolation"] +
        profile["road_risk"] * graph["risk_road"] +
        profile["flood"] * graph["risk_flood"] +
        profile["cctv"] * graph["risk_cctv"] +
        profile["police_dist"] * graph["risk_police"] +
        profile["time_risk"] * graph["risk_timebase"] +
        profile["dynamic"] * dynamic
    ) / weight_sum

    cost = graph["edge_time_s"] * (1.0 + profile["risk_scale"] * composite_risk)

    if incident_multiplier is not None:
        cost = cost * incident_multiplier

    cost = cost.copy()
    if closed_edges:
        closed_idx = np.array(list(closed_edges), dtype=np.int64)
        closed_idx = closed_idx[(closed_idx >= 0) & (closed_idx < graph["num_edges"])]
        cost[closed_idx] = np.inf

    return cost, composite_risk


# --------------------------------------------------------------------------
# A* ROUTING
# --------------------------------------------------------------------------

def a_star(
    graph: Dict,
    start_idx: int,
    goal_idx: int,
    mode: str = "balanced",
    hour: int = 12,
    incidents: Optional[List[Dict]] = None,
    closed_edges: Optional[List[int]] = None,
) -> Optional[Dict]:
    """Optimized A* with Haversine heuristic over dynamic, in-memory-only
    edge costs. Returns None if no path exists."""
    t0 = time.perf_counter()

    incident_mult, incident_affected_mask = build_incident_multiplier(graph, incidents)
    edge_cost_arr, composite_risk_arr = compute_edge_costs(graph, mode, hour, incident_mult, closed_edges)

    lat, lng = graph["lat"], graph["lng"]
    v_max = graph["v_max_mps"]
    goal_lat, goal_lng = lat[goal_idx], lng[goal_idx]

    def heuristic(n: int) -> float:
        return haversine_scalar(lat[n], lng[n], goal_lat, goal_lng) / v_max

    g_score = {start_idx: 0.0}
    came_from: Dict[int, Tuple[int, int]] = {}  # node -> (prev_node, edge_idx)
    open_heap = [(heuristic(start_idx), start_idx)]
    closed_set = set()

    adjacency = graph["adjacency"]

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in closed_set:
            continue
        if current == goal_idx:
            break
        closed_set.add(current)

        for neighbor, edge_idx in adjacency[current]:
            w = edge_cost_arr[edge_idx]
            if not math.isfinite(w):
                continue
            tentative_g = g_score[current] + w
            if tentative_g < g_score.get(neighbor, math.inf):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = (current, edge_idx)
                f = tentative_g + heuristic(neighbor)
                heapq.heappush(open_heap, (f, neighbor))
    else:
        if goal_idx not in g_score:
            return None

    if goal_idx not in g_score:
        return None

    # reconstruct path
    path_nodes = [goal_idx]
    path_edges: List[int] = []
    node = goal_idx
    while node != start_idx:
        prev, edge_idx = came_from[node]
        path_edges.append(edge_idx)
        path_nodes.append(prev)
        node = prev
    path_nodes.reverse()
    path_edges.reverse()

    total_distance = float(np.sum(graph["edge_length_m"][path_edges])) if path_edges else 0.0
    total_time = float(np.sum(graph["edge_time_s"][path_edges])) if path_edges else 0.0
    avg_risk = float(np.mean(composite_risk_arr[path_edges])) if path_edges else 0.0

    exec_time_ms = (time.perf_counter() - t0) * 1000.0

    coordinates = [[float(lat[n]), float(lng[n])] for n in path_nodes]

    incidents_applied = bool(incidents)
    route_hits_incident = bool(incident_affected_mask[path_edges].any()) if (incidents_applied and path_edges) else False

    return {
        "mode": mode, "hour": int(hour) % NUM_HOURS,
        "path_nodes": path_nodes, "path_edges": path_edges,
        "coordinates": coordinates,
        "distance_m": round(total_distance, 2),
        "travel_time_s": round(total_time, 2),
        "risk_score": round(avg_risk, 4),
        "estimated_duration_s": round(total_time * (1.0 + 0.15 * avg_risk), 2),
        "execution_time_ms": round(exec_time_ms, 3),
        "incidents_applied": incidents_applied,
        "incident_avoided": (not route_hits_incident) if incidents_applied else True,
        "closed_edges_applied": bool(closed_edges),
    }


# --------------------------------------------------------------------------
# ROUTE EXPLANATION
# --------------------------------------------------------------------------

MODE_REASONS = {
    "fastest": "Chosen for minimum travel time with only baseline hazard avoidance.",
    "safest": "Chosen to minimize crime, darkness, isolation and flood exposure, accepting extra time.",
    "balanced": "Chosen as a middle ground between travel time and route safety.",
    "women_safety": "Chosen to maximize lighting, CCTV coverage and proximity to police, minimizing isolation.",
    "emergency": "Chosen for the fastest viable path to safety while still avoiding closures and hazards.",
}


def explain_route(graph: Dict, route: Dict) -> Dict:
    edges = route["path_edges"]
    if edges:
        avg_lighting = float(np.mean(graph["lighting_raw"][edges]))
        avg_crime = float(np.mean(graph["crime_raw"][edges]))
        avg_congestion = float(np.mean(graph["hourly_matrix"][edges, route["hour"]]))
    else:
        avg_lighting = avg_crime = avg_congestion = 0.0

    safe_havens_passed = sum(1 for n in route["path_nodes"] if n in graph["safe_haven_indices"])

    return {
        "mode": route["mode"],
        "distance_m": route["distance_m"],
        "travel_time_s": route["travel_time_s"],
        "risk_score": route["risk_score"],
        "avg_lighting": round(avg_lighting, 3),
        "avg_crime": round(avg_crime, 3),
        "avg_congestion": round(avg_congestion, 3),
        "safe_havens_passed": safe_havens_passed,
        "incident_avoidance": route["incident_avoided"],
        "reason": MODE_REASONS.get(route["mode"], "Route selected using the requested mode's cost profile."),
    }


# --------------------------------------------------------------------------
# SAFE HAVEN / SOS ROUTING
# --------------------------------------------------------------------------

def nearest_safe_havens(graph: Dict, node_idx: int, k: int = 3) -> List[Dict]:
    if not graph["safe_haven_indices"] or graph["safe_haven_kdtree"] is None:
        return []
    px, py = graph["proj_x"][node_idx], graph["proj_y"][node_idx]
    k = min(k, len(graph["safe_haven_indices"]))
    dists, idxs = graph["safe_haven_kdtree"].query([px, py], k=k)
    if k == 1:
        dists, idxs = [dists], [idxs]
    results = []
    sh_arr = graph["safe_haven_indices"]
    for d, i in zip(np.atleast_1d(dists), np.atleast_1d(idxs)):
        node = sh_arr[int(i)]
        results.append({
            "node": int(node),
            "lat": float(graph["lat"][node]),
            "lng": float(graph["lng"][node]),
            "type": graph["safe_haven_types"].get(int(node), "unspecified"),
            "straight_line_distance_m": round(float(d), 1),
        })
    return results


def sos_route(graph: Dict, lat: float, lng: float, hour: int = 12) -> Dict:
    start_idx, snap_dist = nearest_node(graph, lat, lng)
    candidates = nearest_safe_havens(graph, start_idx, k=3)
    if not candidates:
        return {"error": "No safe havens available in graph."}

    best_route = None
    best_haven = None
    for cand in candidates:
        route = a_star(graph, start_idx, cand["node"], mode="emergency", hour=hour)
        if route and (best_route is None or route["travel_time_s"] < best_route["travel_time_s"]):
            best_route, best_haven = route, cand

    if best_route is None:
        return {"error": "No reachable safe haven found."}

    return {
        "sos_from": [lat, lng],
        "snapped_node_distance_m": round(snap_dist, 1),
        "nearest_safe_havens": candidates,
        "selected_haven": best_haven,
        "route": best_route,
        "explanation": explain_route(graph, best_route),
    }


# --------------------------------------------------------------------------
# TIME MACHINE ROUTING
# --------------------------------------------------------------------------

def time_machine_route(graph: Dict, start_idx: int, goal_idx: int, current_hour: int,
                        future_hour: int, mode: str = "balanced") -> Dict:
    current_route = a_star(graph, start_idx, goal_idx, mode=mode, hour=current_hour)
    future_route = a_star(graph, start_idx, goal_idx, mode=mode, hour=future_hour)

    result = {
        "mode": mode,
        "current_hour": int(current_hour) % NUM_HOURS,
        "future_hour": int(future_hour) % NUM_HOURS,
        "current_route": current_route,
        "future_route": future_route,
    }
    if current_route and future_route:
        result["delta"] = {
            "distance_diff_m": round(future_route["distance_m"] - current_route["distance_m"], 2),
            "travel_time_diff_s": round(future_route["travel_time_s"] - current_route["travel_time_s"], 2),
            "risk_diff": round(future_route["risk_score"] - current_route["risk_score"], 4),
        }
    return result


# --------------------------------------------------------------------------
# PREDICTIVE RISK (same path, all 24 hours)
# --------------------------------------------------------------------------

def predictive_risk_along_route(graph: Dict, route: Dict) -> Dict:
    edges = route["path_edges"]
    hourly_risk = {}
    if edges:
        for h in range(NUM_HOURS):
            hourly_risk[f"hour_{h:02d}"] = round(float(np.mean(graph["hourly_matrix"][edges, h])), 4)
    else:
        for h in range(NUM_HOURS):
            hourly_risk[f"hour_{h:02d}"] = 0.0

    if hourly_risk:
        safest_hour = min(hourly_risk, key=hourly_risk.get)
        riskiest_hour = max(hourly_risk, key=hourly_risk.get)
    else:
        safest_hour = riskiest_hour = None

    return {
        "mode": route["mode"],
        "hourly_risk": hourly_risk,
        "safest_hour": safest_hour,
        "riskiest_hour": riskiest_hour,
    }


# --------------------------------------------------------------------------
# MULTI-MODE + EMERGENCY BUNDLE
# --------------------------------------------------------------------------

def route_all_modes(graph: Dict, start_idx: int, goal_idx: int, hour: int,
                     incidents: Optional[List[Dict]] = None,
                     closed_edges: Optional[List[int]] = None) -> Dict[str, Optional[Dict]]:
    return {
        mode: a_star(graph, start_idx, goal_idx, mode=mode, hour=hour,
                     incidents=incidents, closed_edges=closed_edges)
        for mode in MODE_PROFILES
    }


# --------------------------------------------------------------------------
# JSON OUTPUT BUILDERS
# --------------------------------------------------------------------------

def write_json(obj: Dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def build_outputs(graph: Dict, route: Dict, output_dir: Path,
                   time_machine: Optional[Dict] = None,
                   emergency: Optional[Dict] = None) -> None:
    explanation = explain_route(graph, route)
    predictive = predictive_risk_along_route(graph, route)

    write_json({
        "mode": route["mode"], "hour": route["hour"],
        "distance_m": route["distance_m"], "travel_time_s": route["travel_time_s"],
        "risk_score": route["risk_score"], "estimated_duration_s": route["estimated_duration_s"],
        "execution_time_ms": route["execution_time_ms"], "node_count": len(route["path_nodes"]),
    }, output_dir / "route_summary.json")

    write_json({"mode": route["mode"], "coordinates": route["coordinates"]},
               output_dir / "route_coordinates.json")

    write_json(explanation, output_dir / "route_explanation.json")
    write_json(predictive, output_dir / "predictive_risk.json")

    if time_machine is not None:
        write_json(time_machine, output_dir / "time_machine.json")
    if emergency is not None:
        write_json(emergency, output_dir / "emergency_routes.json")


# --------------------------------------------------------------------------
# CLI / DEMO ENTRYPOINT
# --------------------------------------------------------------------------

def _parse_incidents_arg(raw: Optional[str]) -> Optional[List[Dict]]:
    if not raw:
        return None
    return json.loads(raw)


def _parse_closed_edges_arg(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    return [int(x) for x in raw.split(",") if x.strip() != ""]


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeRoute-AI v8 routing engine")
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--slat", type=float, default=None)
    parser.add_argument("--slng", type=float, default=None)
    parser.add_argument("--elat", type=float, default=None)
    parser.add_argument("--elng", type=float, default=None)
    parser.add_argument("--source-area", type=str, default=None,
                         help="Area name or list-number; skips the interactive prompt if given.")
    parser.add_argument("--dest-area", type=str, default=None,
                         help="Area name or list-number; skips the interactive prompt if given.")
    parser.add_argument("--mode", type=str, default="balanced", choices=list(MODE_PROFILES.keys()))
    parser.add_argument("--hour", type=int, default=time.localtime().tm_hour)
    parser.add_argument("--future-hour", type=int, default=None)
    parser.add_argument("--incidents", type=str, default=None, help="JSON list of {lat,lng,radius_m,severity}")
    parser.add_argument("--closed-edges", type=str, default=None, help="Comma-separated edge_id list")
    parser.add_argument("--sos", action="store_true", help="Route to nearest safe haven instead of a fixed destination")
    parser.add_argument("--all-modes", action="store_true", help="Compute every routing mode for the same OD pair")
    parser.add_argument("--output-dir", type=str, default="./saferoute_output")
    args = parser.parse_args()

    graph = load_graph(Path(args.data_dir) if args.data_dir else None)
    validate_graph(graph)
    log_startup_summary(graph)

    output_dir = Path(args.output_dir)

    # ----------------------------------------------------------------------
    # STEPS 2-4: dynamic area-selection workflow. This is the ONLY change
    # to how start/goal are obtained -- routing (A*, dynamic costs, SOS,
    # time machine, JSON outputs) below is completely unmodified.
    # If explicit --slat/--slng/--elat/--elng are supplied, those still take
    # priority (direct coordinate override), preserving prior behavior.
    # ----------------------------------------------------------------------
    source_area = dest_area = None
    source_node_idx = goal_node_idx = None
    need_source = args.slat is None or args.slng is None
    need_goal = args.elat is None or args.elng is None

    if need_source or need_goal:
        area_index = load_area_index(Path(args.data_dir) if args.data_dir else None)
        available_areas = area_index["available_areas"]
        if not available_areas:
            raise RuntimeError("No areas could be detected from graph_edges.csv.")

        if need_source:
            if args.source_area:
                source_area = (available_areas[int(args.source_area) - 1]
                                if args.source_area.isdigit() else args.source_area)
            else:
                source_area = prompt_select_area(available_areas, "Source Area")
            source_node_idx, s_lat, s_lng = resolve_area_to_node(graph, area_index, source_area)
            args.slat, args.slng = s_lat, s_lng

        if need_goal:
            if args.dest_area:
                dest_area = (available_areas[int(args.dest_area) - 1]
                              if args.dest_area.isdigit() else args.dest_area)
            else:
                dest_area = prompt_select_area(available_areas, "Destination Area")
            goal_node_idx, e_lat, e_lng = resolve_area_to_node(graph, area_index, dest_area)
            args.elat, args.elng = e_lat, e_lng

    incidents = _parse_incidents_arg(args.incidents) or graph["default_incidents"] or None
    closed_edges = _parse_closed_edges_arg(args.closed_edges)

    t_route0 = time.perf_counter()
    start_idx = source_node_idx if source_node_idx is not None else nearest_node(graph, args.slat, args.slng)[0]

    if args.sos:
        emergency = sos_route(graph, args.slat, args.slng, hour=args.hour)
        print(f"Routing Time: {(time.perf_counter() - t_route0) * 1000:.3f} ms")
        write_json(emergency, output_dir / "emergency_routes.json")
        print(json.dumps(emergency, indent=2)[:2000])
        return

    goal_idx = goal_node_idx if goal_node_idx is not None else nearest_node(graph, args.elat, args.elng)[0]

    if args.all_modes:
        results = route_all_modes(graph, start_idx, goal_idx, args.hour, incidents, closed_edges)
        print(f"Routing Time: {(time.perf_counter() - t_route0) * 1000:.3f} ms")
        for mode, route in results.items():
            if route is None:
                print(f"[{mode}] no path found")
                continue
            write_json(route, output_dir / f"route_{mode}.json")
            print(f"[{mode}] distance={route['distance_m']}m time={route['travel_time_s']}s "
                  f"risk={route['risk_score']} exec={route['execution_time_ms']}ms")
        primary = results.get(args.mode) or next((r for r in results.values() if r), None)
        if primary is None:
            print("No path found for any mode between the given points.")
            return
        route = primary
    else:
        route = a_star(graph, start_idx, goal_idx, mode=args.mode, hour=args.hour,
                        incidents=incidents, closed_edges=closed_edges)
        print(f"Routing Time: {(time.perf_counter() - t_route0) * 1000:.3f} ms")
        if route is None:
            print("No path found between the given points.")
            return

    time_machine = None
    if args.future_hour is not None:
        time_machine = time_machine_route(graph, start_idx, goal_idx, args.hour, args.future_hour, mode=args.mode)

    emergency = sos_route(graph, args.slat, args.slng, hour=args.hour)

    # STEP 7: post-routing summary display.
    print("\n--- Route Summary ---")
    print(f"Source Area: {source_area if source_area else '(explicit coordinates)'}")
    print(f"Destination Area: {dest_area if dest_area else '(explicit coordinates)'}")
    print(f"Representative Node IDs: {int(graph['node_ids'][start_idx])} -> {int(graph['node_ids'][goal_idx])}")
    print(f"Distance: {route['distance_m']} m")
    print(f"Travel Time: {route['travel_time_s']} s")
    print(f"Risk Score: {route['risk_score']}")
    print(f"Execution Time: {route['execution_time_ms']} ms")
    print(f"Routing Mode: {route['mode']}")

    build_outputs(graph, route, output_dir, time_machine=time_machine, emergency=emergency)
    print(f"Outputs written to {output_dir.resolve()}")


if __name__ == "__main__":
    main()
