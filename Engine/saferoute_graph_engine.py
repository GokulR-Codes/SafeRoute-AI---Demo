import sys
import time
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from pathlib import Path

INPUT_CSV = Path(r"D:\Project\SafeRoute - Demo\Datasets\Lat-Lon\central_bangalore_main_cluster.csv")
OUTPUT_DIR = Path(r"D:\Project\SafeRoute - Demo\Datasets\Edges - Weights")
K_NEIGHBORS = 3
EARTH_R_M = 6371000.0

HOUR_RISK_MULTIPLIERS = np.array([
    1.35, 1.35, 1.35, 1.35, 1.35,
    1.10, 1.10,
    1.20, 1.20, 1.20,
    1.00, 1.00, 1.00, 1.00, 1.00, 1.00,
    1.25, 1.25, 1.25, 1.25,
    1.10, 1.10,
    1.30, 1.30,
])


class UnionFind:
    __slots__ = ("parent", "rank")

    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def haversine_vec(lat1, lon1, lat2, lon2):
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlmb / 2.0) ** 2
    return 2.0 * EARTH_R_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def build_graph_files(df: pd.DataFrame, output_dir: Path) -> dict:
    """Build graph_nodes/edges/hourly CSVs from a raw points DataFrame.

    `df` carries the same columns as central_bangalore_main_cluster.csv (one row
    per point: lat, lng, and the risk-factor attributes). This is used both by
    the CLI below (reading INPUT_CSV) and by the backend (feeding rows straight
    from MongoDB), so the graph comes out identical either way.

    Returns a summary dict; writes the three CSVs into `output_dir`.
    """
    t0 = time.time()

    df = df.reset_index(drop=True)

    if "road_name" in df.columns:
        df["road_name"] = df["road_name"].fillna("Unnamed Road")
    df = df.fillna(0)

    lat_r = df["lat"].round(7)
    lng_r = df["lng"].round(7)

    unique_map = {}
    node_id_list = []
    for la, ln in zip(lat_r, lng_r):
        key = (la, ln)
        nid = unique_map.get(key)
        if nid is None:
            nid = len(unique_map)
            unique_map[key] = nid
        node_id_list.append(nid)
    df["node_id"] = node_id_list
    n = len(unique_map)

    node_lat = np.zeros(n)
    node_lng = np.zeros(n)
    for (la, ln), i in unique_map.items():
        node_lat[i] = la
        node_lng[i] = ln
    xy = np.column_stack([node_lat, node_lng])

    attr_cols = [c for c in df.columns if c not in ("node_id", "lat", "lng")]
    numeric_cols = [c for c in attr_cols if pd.api.types.is_numeric_dtype(df[c])]
    categorical_cols = [c for c in attr_cols if c not in numeric_cols]

    grouped_num = (
        df.groupby("node_id")[numeric_cols].mean().reindex(range(n)).fillna(0.0)
        if numeric_cols else pd.DataFrame(index=range(n))
    )
    grouped_cat = (
        df.groupby("node_id")[categorical_cols].agg(lambda s: s.iloc[0]).reindex(range(n))
        if categorical_cols else pd.DataFrame(index=range(n))
    )

    node_num_arrays = {c: grouped_num[c].to_numpy() for c in numeric_cols}
    node_cat_arrays = {c: grouped_cat[c].to_numpy() for c in categorical_cols}

    k = min(K_NEIGHBORS + 1, n)
    tree = cKDTree(xy)
    dist, idx = tree.query(xy, k=k)
    if idx.ndim == 1:
        idx = idx.reshape(-1, 1)

    uf = UnionFind(n)
    edge_set = set()
    for i in range(n):
        for j in idx[i]:
            j = int(j)
            if j == i:
                continue
            a, b = (i, j) if i < j else (j, i)
            if (a, b) not in edge_set:
                edge_set.add((a, b))
                uf.union(a, b)

    static_comp = np.array([uf.find(i) for i in range(n)], dtype=np.int64)
    _, static_comp = np.unique(static_comp, return_inverse=True)
    n_static_comp = int(static_comp.max() + 1) if n > 0 else 0

    comp_roots = np.array([uf.find(i) for i in range(n)], dtype=np.int64)
    unique_roots, counts = np.unique(comp_roots, return_counts=True)
    if len(unique_roots) > 1:
        main_root = unique_roots[np.argmax(counts)]
        main_idx = np.where(comp_roots == main_root)[0]
        main_tree = cKDTree(xy[main_idx])
        for root in unique_roots:
            if root == main_root:
                continue
            other_idx = np.where(comp_roots == root)[0]
            d, pos = main_tree.query(xy[other_idx])
            best = int(np.argmin(d))
            u_local = int(other_idx[best])
            v_local = int(main_idx[pos[best]])
            a, b = (u_local, v_local) if u_local < v_local else (v_local, u_local)
            if (a, b) not in edge_set:
                edge_set.add((a, b))
                uf.union(a, b)

    graph_comp = np.array([uf.find(i) for i in range(n)], dtype=np.int64)
    _, graph_comp = np.unique(graph_comp, return_inverse=True)
    n_graph_comp = int(graph_comp.max() + 1) if n > 0 else 0

    edges = np.array(sorted(edge_set), dtype=np.int64)
    E = len(edges)
    u_arr, v_arr = edges[:, 0], edges[:, 1]

    lat_u, lng_u = xy[u_arr, 0], xy[u_arr, 1]
    lat_v, lng_v = xy[v_arr, 0], xy[v_arr, 1]
    edge_length_m = haversine_vec(lat_u, lng_u, lat_v, lng_v)

    def avg_col(name, default):
        arr = node_num_arrays.get(name)
        if arr is None:
            return np.full(E, default)
        return (arr[u_arr] + arr[v_arr]) / 2.0

    speed_limit = avg_col("speed_limit", 30.0)
    speed_limit = np.where(speed_limit <= 0, 30.0, speed_limit)
    speed_mps = np.maximum(speed_limit, 5.0) * 1000.0 / 3600.0
    estimated_travel_time = edge_length_m / speed_mps

    road_risk = avg_col("road_risk_score", 0.3)
    congestion = avg_col("congestion_score", 0.3)
    routing_cost = edge_length_m * (1.0 + road_risk + 0.5 * congestion)
    static_cost = edge_length_m

    crime_score = avg_col("crime_score", 0.3)
    lighting_score = avg_col("lighting_score", 0.5)
    cctv_density = avg_col("cctv_density_estimate", 0.5)
    safety_index = lighting_score + cctv_density - road_risk - crime_score
    zone_type = np.where(
        safety_index >= 0.3, "SafeZone",
        np.where(safety_index <= -0.3, "DangerZone", "ModerateZone")
    )

    edge_id = np.arange(E)
    edges_data = {
        "edge_id": edge_id,
        "u": u_arr,
        "v": v_arr,
        "edge_length_m": np.round(edge_length_m, 2),
        "estimated_travel_time": np.round(estimated_travel_time, 2),
        "routing_cost": np.round(routing_cost, 2),
        "static_cost": np.round(static_cost, 2),
    }
    for c in numeric_cols:
        edges_data[c] = np.round(avg_col(c, 0.0), 4)
    for c in categorical_cols:
        arr = node_cat_arrays[c]
        edges_data[c] = arr[u_arr]
    edges_data["zone_type"] = zone_type
    edges_data["static_component"] = static_comp[u_arr]
    edges_data["graph_component"] = graph_comp[u_arr]

    edges_df = pd.DataFrame(edges_data)

    degree = np.zeros(n, dtype=np.int64)
    np.add.at(degree, u_arr, 1)
    np.add.at(degree, v_arr, 1)

    hosp_arr = node_num_arrays.get("hospital_density", np.zeros(n))
    police_arr = node_num_arrays.get("police_station_distance", np.full(n, 999.0))
    hosp_thr = np.quantile(hosp_arr, 0.85) if np.any(hosp_arr) else float("inf")
    police_thr = np.quantile(police_arr, 0.15)
    is_safe_haven = ((hosp_arr >= hosp_thr) | (police_arr <= police_thr)).astype(int)

    nodes_df = pd.DataFrame({
        "node_id": np.arange(n),
        "lat": node_lat,
        "lng": node_lng,
        "degree": degree,
        "is_safe_haven": is_safe_haven,
        "static_component": static_comp,
        "graph_component": graph_comp,
    })

    if "road_risk_score" in edges_df.columns:
        base_risk = edges_df["road_risk_score"].to_numpy()
    elif "time_risk" in edges_df.columns:
        base_risk = edges_df["time_risk"].to_numpy()
    else:
        base_risk = np.full(E, 0.3)

    hourly_matrix = np.outer(base_risk, HOUR_RISK_MULTIPLIERS)
    hourly_data = {"edge_id": edge_id}
    for h in range(24):
        hourly_data[f"hour_{h:02d}"] = np.round(hourly_matrix[:, h], 4)
    hourly_df = pd.DataFrame(hourly_data)

    assert nodes_df["node_id"].duplicated().sum() == 0
    assert edges_df[["u", "v"]].duplicated().sum() == 0
    valid_nodes = set(nodes_df["node_id"].tolist())
    assert set(u_arr.tolist()).issubset(valid_nodes)
    assert set(v_arr.tolist()).issubset(valid_nodes)
    assert nodes_df[["lat", "lng"]].isna().sum().sum() == 0
    assert not edges_df.isna().any().any()
    assert not hourly_df.isna().any().any()
    assert len(hourly_df) == len(edges_df)

    counts_final = np.bincount(graph_comp)
    largest_component_size = int(counts_final.max()) if len(counts_final) else 0
    largest_pct = 100.0 * largest_component_size / n if n else 0.0
    avg_degree = float(2 * E / n) if n else 0.0

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_df.to_csv(output_dir / "graph_nodes.csv", index=False)
    edges_df.to_csv(output_dir / "graph_edges.csv", index=False)
    hourly_df.to_csv(output_dir / "hourly_edge_weights.csv", index=False)

    elapsed = time.time() - t0
    return {
        "nodes": n,
        "edges": E,
        "static_components": n_static_comp,
        "connected_components": n_graph_comp,
        "largest_component": largest_component_size,
        "largest_pct": largest_pct,
        "avg_degree": avg_degree,
        "safe_havens": int(is_safe_haven.sum()),
        "elapsed_s": elapsed,
    }


def main():
    df = pd.read_csv(INPUT_CSV)
    stats = build_graph_files(df, OUTPUT_DIR)
    print("=== SafeRoute-AI v8 Graph Generation Summary ===")
    print(f"Nodes: {stats['nodes']}")
    print(f"Edges: {stats['edges']}")
    print(f"Static components (pre-bridge): {stats['static_components']}")
    print(f"Connected components (final): {stats['connected_components']}")
    print(f"Largest component: {stats['largest_component']} ({stats['largest_pct']:.2f}%)")
    print(f"Average node degree: {stats['avg_degree']:.2f}")
    print(f"Safe havens flagged: {stats['safe_havens']}")
    print(f"Execution time: {stats['elapsed_s']:.2f}s")
    print("Validation: PASSED")


if __name__ == "__main__":
    main()
