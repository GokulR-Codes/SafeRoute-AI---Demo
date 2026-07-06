"""
SafeRoute-AI Backend
=====================
Thin FastAPI wrapper around the existing `safe_route_engine.py`. It never
modifies, reimplements, or duplicates any routing/risk logic -- it loads the
graph once at startup (in-process, no subprocess) and calls straight into
the engine's own functions for every request.

Configure via environment variables (all optional, defaults match the
project layout on disk):

    SAFEROUTE_ENGINE_DIR   Folder containing safe_route_engine.py
                           (default: D:\\Project\\SafeRoute - Demo\\Engine)
    SAFEROUTE_DATA_DIR     Folder containing graph_nodes.csv / graph_edges.csv /
                           hourly_edge_weights.csv. If unset, the engine's own
                           built-in default is used.
    SAFEROUTE_OUTPUT_DIR   Folder every generated route is written to
                           (default: D:\\Project\\SafeRoute - Demo\\Routes)

Run with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENGINE_DIR = Path(os.environ.get("SAFEROUTE_ENGINE_DIR", r"D:\Project\SafeRoute - Demo\Engine"))
DATA_DIR_ENV = os.environ.get("SAFEROUTE_DATA_DIR")  # None -> engine's own default
OUTPUT_DIR = Path(os.environ.get("SAFEROUTE_OUTPUT_DIR", r"D:\Project\SafeRoute - Demo\Routes"))

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import safe_route_engine as engine  # noqa: E402  (sys.path must be set first)

# In-memory state populated once at startup.
state: Dict[str, Any] = {
    "graph": None,
    "area_index": None,
    "status": {
        "backend_connected": True,
        "graph_loaded": False,
        "routing_engine_ready": False,
        "risk_engine_ready": False,
    },
    "error": None,
}


def _data_dir() -> Optional[Path]:
    return Path(DATA_DIR_ENV) if DATA_DIR_ENV else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        graph = engine.load_graph(_data_dir())
        engine.validate_graph(graph)
        engine.log_startup_summary(graph)

        try:
            area_index = engine.load_area_index(_data_dir())
        except (FileNotFoundError, ValueError) as exc:
            # Areas are a convenience layer on top of graph_edges.csv; if the
            # columns aren't present, routing itself still works via raw
            # lat/lng, so we degrade gracefully instead of failing startup.
            area_index = None
            state["error"] = f"Area index unavailable: {exc}"

        state["graph"] = graph
        state["area_index"] = area_index
        state["status"] = {
            "backend_connected": True,
            "graph_loaded": True,
            "routing_engine_ready": True,
            "risk_engine_ready": True,
            "node_count": graph["num_nodes"],
            "edge_count": graph["num_edges"],
            "area_count": len(area_index["available_areas"]) if area_index else 0,
        }
    except Exception as exc:  # noqa: BLE001
        state["error"] = str(exc)
        state["status"] = {
            "backend_connected": True,
            "graph_loaded": False,
            "routing_engine_ready": False,
            "risk_engine_ready": False,
        }

    yield
    # No teardown needed -- the graph is just an in-memory dict.


app = FastAPI(title="SafeRoute-AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_graph() -> Dict:
    if state["graph"] is None:
        raise HTTPException(status_code=503, detail=f"Engine not ready: {state['error'] or 'still loading'}")
    return state["graph"]


# ---------------------------------------------------------------------------
# Status + areas
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status() -> Dict:
    return state["status"]


@app.get("/api/areas")
def get_areas() -> Dict:
    _require_graph()
    if state["area_index"] is None:
        raise HTTPException(
            status_code=503,
            detail="graph_edges.csv has none of source_area/destination_area/road_name/zone columns.",
        )
    return {"areas": state["area_index"]["available_areas"]}


@app.get("/api/modes")
def get_modes() -> Dict:
    return {"modes": list(engine.MODE_PROFILES.keys())}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    source_area: Optional[str] = None
    dest_area: Optional[str] = None
    slat: Optional[float] = None
    slng: Optional[float] = None
    elat: Optional[float] = None
    elng: Optional[float] = None
    mode: str = "balanced"
    hour: Optional[int] = None
    future_hour: Optional[int] = None


def _resolve_point(graph: Dict, area_index: Optional[Dict], area: Optional[str],
                    lat: Optional[float], lng: Optional[float], label: str):
    if area:
        if area_index is None:
            raise HTTPException(status_code=400, detail="Area index unavailable; pass explicit lat/lng instead.")
        try:
            idx, r_lat, r_lng = engine.resolve_area_to_node(graph, area_index, area)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return idx, r_lat, r_lng
    if lat is not None and lng is not None:
        idx, _dist = engine.nearest_node(graph, lat, lng)
        return idx, lat, lng
    raise HTTPException(status_code=400, detail=f"Provide {label}_area or {label[0]}lat/{label[0]}lng.")


@app.post("/api/route")
def post_route(req: RouteRequest) -> Dict:
    graph = _require_graph()
    area_index = state["area_index"]

    if req.mode not in engine.MODE_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{req.mode}'. Valid: {list(engine.MODE_PROFILES)}")

    hour = req.hour if req.hour is not None else time.localtime().tm_hour

    start_idx, s_lat, s_lng = _resolve_point(graph, area_index, req.source_area, req.slat, req.slng, "source")
    goal_idx, e_lat, e_lng = _resolve_point(graph, area_index, req.dest_area, req.elat, req.elng, "dest")

    incidents = graph["default_incidents"] or None
    route = engine.a_star(graph, start_idx, goal_idx, mode=req.mode, hour=hour, incidents=incidents)
    if route is None:
        raise HTTPException(status_code=404, detail="No path found between the selected areas.")

    time_machine = None
    if req.future_hour is not None:
        time_machine = engine.time_machine_route(graph, start_idx, goal_idx, hour, req.future_hour, mode=req.mode)

    emergency = engine.sos_route(graph, s_lat, s_lng, hour=hour)
    explanation = engine.explain_route(graph, route)
    predictive = engine.predictive_risk_along_route(graph, route)

    # Writes route_summary.json / route_coordinates.json / route_explanation.json /
    # predictive_risk.json (+ time_machine.json / emergency_routes.json) to
    # SAFEROUTE_OUTPUT_DIR, exactly as the CLI does.
    engine.build_outputs(graph, route, OUTPUT_DIR, time_machine=time_machine, emergency=emergency)

    safe_havens_on_route = [
        {
            "node": int(n),
            "lat": float(graph["lat"][n]),
            "lng": float(graph["lng"][n]),
            "type": graph["safe_haven_types"].get(int(n), "unspecified"),
        }
        for n in route["path_nodes"] if n in graph["safe_haven_indices"]
    ]

    return {
        "source": {"area": req.source_area, "lat": s_lat, "lng": s_lng},
        "dest": {"area": req.dest_area, "lat": e_lat, "lng": e_lng},
        "route": route,
        "summary": {
            "mode": route["mode"], "hour": route["hour"],
            "distance_m": route["distance_m"], "travel_time_s": route["travel_time_s"],
            "risk_score": route["risk_score"], "estimated_duration_s": route["estimated_duration_s"],
            "execution_time_ms": route["execution_time_ms"], "node_count": len(route["path_nodes"]),
        },
        "explanation": explanation,
        "predictive_risk": predictive,
        "emergency": emergency,
        "time_machine": time_machine,
        "incidents": incidents or [],
        "safe_havens_on_route": safe_havens_on_route,
        "output_dir": str(OUTPUT_DIR.resolve()) if OUTPUT_DIR.exists() or True else None,
    }


class SosRequest(BaseModel):
    slat: float
    slng: float
    hour: Optional[int] = None


@app.post("/api/sos")
def post_sos(req: SosRequest) -> Dict:
    graph = _require_graph()
    hour = req.hour if req.hour is not None else time.localtime().tm_hour
    result = engine.sos_route(graph, req.slat, req.slng, hour=hour)
    engine.write_json(result, OUTPUT_DIR / "emergency_routes.json")
    return result


@app.get("/api/latest")
def get_latest() -> Dict:
    """Reads whatever is currently sitting in the Routes output directory."""
    files = [
        "route_summary.json", "route_coordinates.json", "route_explanation.json",
        "predictive_risk.json", "time_machine.json", "emergency_routes.json",
    ]
    out: Dict[str, Any] = {}
    for fname in files:
        p = OUTPUT_DIR / fname
        if p.exists():
            out[fname.replace(".json", "")] = json.loads(p.read_text())
    return out
