# SafeRoute-AI

A map-first web app for the existing SafeRoute routing engine. The engine
(`safe_route_engine.py`) is never modified — this adds two things around it:

- **`backend/`** — a thin FastAPI wrapper that imports the engine in-process
  (no subprocess calls) and exposes it over HTTP.
- **`frontend/`** — a Next.js/React/TypeScript app that renders the map,
  route planner, and risk details, matching the provided Figma reference.

## How it fits your project folder

Your layout is:

```
D:\Project\SafeRoute - Demo\
  Datasets\Edges - Weights\      graph_nodes.csv, graph_edges.csv, hourly_edge_weights.csv
  Engine\                        safe_route_engine.py   <- untouched
  Routes\                        every generated route's JSON lands here
  backend\                       <- copy this folder in
  frontend\                      <- copy this folder in
```

Drop the `backend/` and `frontend/` folders from this delivery straight into
`D:\Project\SafeRoute - Demo\`.

## The pipeline, end to end

1. You start the backend. It imports `safe_route_engine.py` from `Engine\`
   and loads the graph from `Datasets\Edges - Weights\` **once**, in memory.
2. You start the frontend and open it in a browser. On load, it asks the
   backend for the list of areas (read from `graph_edges.csv`) and populates
   the source/destination dropdowns — nothing is hardcoded.
3. You pick source, destination, a mode (Fastest / Safest / Balanced /
   Women safety), and generate a route.
4. The backend calls straight into the engine's own `a_star`, `explain_route`,
   `predictive_risk_along_route`, and `sos_route` functions, writes
   `route_summary.json`, `route_coordinates.json`, `route_explanation.json`,
   `predictive_risk.json`, and `emergency_routes.json` into `Routes\`
   (via the engine's own `build_outputs`), and also returns that same data
   to the frontend directly so the map updates instantly.
5. Dragging the hour ribbon at the bottom re-requests the route for that
   hour, using the engine's own time-of-day risk weighting.
6. The red SOS button calls the engine's own `sos_route` to the nearest
   safe haven.

Nothing on screen is invented — every number comes from the JSON shapes
already produced by `safe_route_engine.py` (verified against the sample
outputs you provided).

## 1. Run the backend

Requires Python 3.10+ (whatever you already run the engine with — it needs
`numpy`/`pandas`/`scipy`, which the engine already depends on).

```bat
cd "D:\Project\SafeRoute - Demo\backend"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

set SAFEROUTE_ENGINE_DIR=D:\Project\SafeRoute - Demo\Engine
set SAFEROUTE_DATA_DIR=D:\Project\SafeRoute - Demo\Datasets\Edges - Weights
set SAFEROUTE_OUTPUT_DIR=D:\Project\SafeRoute - Demo\Routes

uvicorn main:app --reload --port 8000
```

If `SAFEROUTE_DATA_DIR` isn't set, it falls back to whatever `DATA_DIR`
default is already hardcoded in `safe_route_engine.py`. If your CSVs live
somewhere else, just point the env var at them — nothing in the engine
needs to change.

Check it worked: open `http://localhost:8000/api/status` — you should see
`"graph_loaded": true"` and real node/edge counts.

## 2. Run the frontend

Requires Node.js 20+.

```bat
cd "D:\Project\SafeRoute - Demo\frontend"
npm install
copy .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## Notes

- **Areas come from `graph_edges.csv`** via the engine's own
  `load_area_index()` (it reads whichever of `source_area` /
  `destination_area` / `road_name` / `zone` columns exist). If none of those
  columns exist in your CSV, `/api/areas` will return a 503 with a clear
  message — routing itself still works, but you'd need to add a lat/lng
  picker instead of area dropdowns (not built, since it's not what your
  data currently supports).
- **`Start navigation`** currently re-centers/fits the map to the route.
  There's no turn-by-turn engine behind it (the backend doesn't have one),
  so it doesn't pretend to.
- I tested `backend/main.py` end-to-end against synthetic CSVs matching your
  exact schema (34 nodes, 35 edges, real area names) and confirmed
  `/api/status`, `/api/areas`, `/api/modes`, and `/api/route` all return
  correct data and that the JSON files land in the output directory. I also
  ran a full `next build` of the frontend and confirmed it compiles cleanly
  end to end.
- I did not have your real `Datasets\Edges - Weights\*.csv` files or a
  Windows machine to test the exact paths on, so the first run is worth
  double-checking against `/api/status` before trusting the UI.
