# Deploying SafeRoute-AI

This guide takes you from the current repo to a live, public URL. It has three
parts you do in order:

1. **Backend** (FastAPI + routing engine) → **Google Cloud Run** (a container).
2. **Frontend** (Next.js) → **Vercel**, pointed at the backend URL.
3. **Database** (MongoDB) → optional risk-factor layer read by the backend.

```
  Browser ──HTTPS──▶ Vercel (Next.js UI)
                        │  NEXT_PUBLIC_API_BASE
                        ▼
                     Cloud Run (FastAPI + safe_route_engine.py + saferoute_graph_engine.py)
                        │  MONGODB_URI (backend only)
                        ▼
                     MongoDB (Central Bangalore points → graph built at startup)
```

> **Why the backend can't go on Vercel:** it loads the whole graph into memory
> **once at startup** and keeps it there for every request. Vercel's serverless
> functions are stateless and cold-start per request, so the graph would reload
> constantly. It also needs `numpy`/`pandas`/`scipy` and reads CSVs from disk.
> A container host (Cloud Run, Render, Railway, Fly) is the right home for it.
> Cloud Run fits well: it runs your Docker image, keeps the container warm
> between requests, and scales to zero if you let it.

---

## What ships where

| Piece | Path in repo | Goes to |
|-------|--------------|---------|
| FastAPI wrapper | `Frontend/saferoute-ai/backend/` | Cloud Run (in Docker image) |
| Routing engine | `Engine/safe_route_engine.py` | Cloud Run (in Docker image) |
| Graph builder | `Engine/saferoute_graph_engine.py` | Cloud Run (in Docker image) |
| Web UI | `Frontend/saferoute-ai/frontend/` | Vercel |

> **No datasets ship in the image.** On Cloud Run the backend runs with
> `SAFEROUTE_GRAPH_SOURCE=mongo`: at startup it pulls the raw Central Bangalore
> points from MongoDB and `saferoute_graph_engine.py` builds the graph
> (`graph_nodes`/`graph_edges`/`hourly_edge_weights`) into `/tmp` in memory,
> then `safe_route_engine.py` routes on it. Verified to reproduce the exact same
> graph as the old CSVs (2929 nodes / 5675 edges / 379 areas).
>
> **This makes MongoDB required for the Cloud Run backend** — if Mongo is
> unreachable at startup, the graph can't build and `/api/status` reports
> `graph_loaded: false`. (Local dev is unaffected: it defaults to
> `SAFEROUTE_GRAPH_SOURCE=csv` and reads the committed CSVs.)

---

## Prerequisites

- A [Google Cloud](https://console.cloud.google.com) project with billing
  enabled, and the [`gcloud` CLI](https://cloud.google.com/sdk/docs/install)
  installed. (Cloud Run has a generous always-free tier, but a billing account
  must be attached.)
- A [Vercel](https://vercel.com) account (free "Hobby" tier is fine). The
  frontend deploys from GitHub, so push the repo there too.
- (Optional, to test the image locally) Docker Desktop.

---

## Part 1 — Deploy the backend to Google Cloud Run

Cloud Run runs the same container the Dockerfile builds. The repo already has
what it needs:

- [`Dockerfile`](Dockerfile) — bundles the wrapper, engine, and datasets. Its
  start command binds to `$PORT`, which Cloud Run injects (8080) — no change needed.
- [`.dockerignore`](.dockerignore) — keeps the frontend out of the build context.
- [`.gcloudignore`](.gcloudignore) — keeps the frontend out of the source
  **upload** (without it, `gcloud` falls back to `.gitignore` and uploads
  `node_modules`).

### One-time setup

```bash
# Install the gcloud CLI, then:
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable the APIs Cloud Run source-deploys need (Cloud Run, Cloud Build, Artifact Registry):
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### Deploy (build + release in one command)

From the **repository root**:

```bash
gcloud run deploy saferoute-api \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 1 \
  --port 8080
```

What each flag does:

| Flag | Why |
|------|-----|
| `--source .` | Cloud Build builds the image from the `Dockerfile` at the repo root (context = the uploaded source). |
| `--region asia-south1` | Mumbai — closest to a Bengaluru dataset. Pick any region you like. |
| `--allow-unauthenticated` | Makes the API publicly reachable so the frontend can call it without auth. |
| `--memory 1Gi` | pandas + scipy + the in-memory graph. 512Mi may work; 1Gi is safe. |
| `--min-instances 1` | Keeps one instance warm so there's **no cold start** (the graph stays loaded). Set to `0` to scale to zero and pay nothing when idle — at the cost of a ~few-second cold start + graph reload on the next request. |
| `--port 8080` | The port the container listens on (matches `$PORT`). |

First deploy takes ~4–6 min (installs numpy/pandas/scipy, then builds the
image). When it finishes, gcloud prints a **Service URL** like
`https://saferoute-api-xxxxxxxx-el.a.run.app` — that's your `NEXT_PUBLIC_API_BASE`.

### Deploy via the Cloud Console (GUI — no CLI)

Prefer clicking? This connects GitHub once and rebuilds your `Dockerfile`
automatically on every push to `main`.

1. **Push the repo to GitHub** (Cloud Build pulls from there).
2. In the Cloud Console, enable the APIs (search each in the top bar → Enable):
   **Cloud Run Admin API**, **Cloud Build API**, **Artifact Registry API**.
3. Go to **Cloud Run** → **Create Service**.
4. Choose **"Continuously deploy from a repository (source or function)"** →
   click **Set up with Cloud Build**.
5. **Repository:** click **Manage connected repositories**, authorize the
   **Google Cloud Build** GitHub app, and select this repo. Back in the panel,
   pick the repo and **Branch:** `^main$`.
6. **Build configuration:**
   - **Build Type:** `Dockerfile`
   - **Source location:** `/Dockerfile` (it's at the repo root)
   - Click **Save**.
7. Back on the service form, set:
   - **Service name:** `saferoute-api`
   - **Region:** `asia-south1 (Mumbai)`
   - **Authentication:** **Allow unauthenticated invocations** (so the frontend
     can reach it).
8. Expand **Containers, Volumes, Networking, Security** → **Container** tab:
   - **Container port:** `8080`
   - **Memory:** `1 GiB`
   - **CPU:** `1`
9. In the same section open the **Autoscaling** settings and set **Minimum
   number of instances:** `1` (keeps it warm — no cold start). Use `0` to scale
   to zero and pay nothing when idle.
10. Click **Create**. Watch the build in **Cloud Build** (~4–6 min the first
    time). When it's live, the service page shows the **URL** at the top — copy
    it; that's your `NEXT_PUBLIC_API_BASE`.

> You don't need to set any environment variables in the GUI — the Dockerfile
> already bakes in `SAFEROUTE_ENGINE_DIR` / `SAFEROUTE_DATA_DIR` /
> `SAFEROUTE_OUTPUT_DIR`. (To override one anyway: **Variables & Secrets** tab →
> **Add variable**.)
>
> `.gcloudignore` doesn't apply to this GitHub path — Cloud Build clones the
> whole repo and uses **`.dockerignore`** to keep the frontend out of the image,
> which the repo already has. `.gcloudignore` only matters for the CLI
> `--source` upload above.

After the first setup, **every push to `main` auto-builds and deploys** a new
revision. To change memory/CPU/min-instances later: **Cloud Run** → the service
→ **Edit & deploy new revision**.

### Environment variables

The Dockerfile sets the graph/engine defaults, so the **only** vars you must add
at deploy time are the three MongoDB ones (see Part 4) — the graph is built from
Mongo, so without them the backend can't boot its graph.

| Variable | Default (in image) | Purpose |
|----------|-------------------|---------|
| `SAFEROUTE_ENGINE_DIR` | `/app/engine` | Folder with the two engine `.py` files |
| `SAFEROUTE_GRAPH_SOURCE` | `mongo` | `mongo` = build graph from the DB at startup; `csv` = read pre-built CSVs |
| `SAFEROUTE_DATA_DIR` | `/tmp/saferoute_graph` | Writable dir the generated graph CSVs are written to (in `mongo` mode) / read from (in `csv` mode) |
| `SAFEROUTE_OUTPUT_DIR` | `/tmp/routes` | Where route JSONs are written (ephemeral — `/tmp` is the only writable path on Cloud Run; fine, since the API also returns the data directly) |
| `MONGODB_URI` / `MONGODB_DB` / `MONGODB_COLLECTION` | *(unset — you provide)* | The DB the graph + risk factors load from. **Required** in `mongo` mode. See Part 4. |
| `PORT` | injected by Cloud Run (8080) | Do **not** set this yourself |

### Verify the backend

```
https://<your-service-url>/api/status
```

Expect `"graph_loaded": true` with real `node_count` / `edge_count` /
`area_count`. Also check `/api/areas`. If `graph_loaded` is `false`, see
Troubleshooting.

### Redeploying after code changes

Re-run the same `gcloud run deploy` command — it rebuilds and rolls out a new
revision with zero downtime.

### Test the image locally first (optional)

The image builds its graph from Mongo, so pass the three DB vars when running it:

```bash
# from the repo root
docker build -t saferoute-api -f Dockerfile .
docker run --rm -e PORT=8080 -p 8080:8080 \
  -e MONGODB_URI='mongodb+srv://...' -e MONGODB_DB='your_db' \
  -e MONGODB_COLLECTION='your_collection' \
  saferoute-api
# then open http://localhost:8080/api/status  (expect graph_loaded: true)
```

<details>
<summary><strong>Alternative: Render</strong> (if you'd rather not use GCP)</summary>

The repo also includes [`render.yaml`](render.yaml). In Render: **New +** →
**Blueprint** → select the repo → **Apply**. Render reads the Blueprint, builds
the same Dockerfile, and gives you a `*.onrender.com` URL. The free tier sleeps
after ~15 min idle (~30–60s cold start); the frontend polls `/api/status` every
15s and recovers on its own.
</details>

---

## Part 2 — Deploy the frontend to Vercel

1. Vercel: **Add New** → **Project** → import this GitHub repo.
2. **Critical — set the Root Directory** to:
   ```
   Frontend/saferoute-ai/frontend
   ```
   (Click "Edit" next to Root Directory during import. Vercel then auto-detects
   Next.js; leave build/output settings at their defaults.)
3. Add an **Environment Variable**:

   | Name | Value |
   |------|-------|
   | `NEXT_PUBLIC_API_BASE` | your Cloud Run service URL (e.g. `https://saferoute-api-xxxxxxxx-el.a.run.app`) |

   (No trailing slash. This is baked in at build time, so if you change it later
   you must redeploy.)
4. Click **Deploy**. Your UI goes live at `https://<project>.vercel.app`.

---

## Part 3 — Lock down CORS (do this once both URLs exist)

The backend currently allows every origin
([`main.py`](Frontend/saferoute-ai/backend/main.py) → `allow_origins=["*"]`),
which is fine for a demo. To restrict it to your Vercel domain, edit that file:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://<project>.vercel.app"],  # was ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Then redeploy the backend: re-run the `gcloud run deploy saferoute-api
--source . ...` command. (You can add multiple origins to the list, e.g. your
Vercel domain plus `http://localhost:3000` for local dev.)

---

## Part 4 — MongoDB (risk-factor collection)

The credentials go on the **backend only** — never the frontend, and never in a
`NEXT_PUBLIC_*` var (those ship to the browser). The browser talks to the
backend; only the backend talks to Mongo.

The code is already wired up ([backend/db.py](Frontend/saferoute-ai/backend/db.py)
+ [backend/main.py](Frontend/saferoute-ai/backend/main.py)):

- On startup it fetches the collection once. Those raw points serve **two**
  purposes: in `mongo` graph mode (the Cloud Run default) they're fed to
  `saferoute_graph_engine.py` to **build the routing graph**, and they're also
  exposed read-only for the map overlay. So on Cloud Run, **routing depends on
  Mongo** — if the DB is unreachable at startup, `graph_loaded` is `false`.
  (Local dev with `SAFEROUTE_GRAPH_SOURCE=csv` routes from the committed CSVs and
  Mongo stays optional.)
- It exposes the data read-only at **`GET /api/risk-factors`**, with optional
  `?zone=`, `?source_area=`, and `?limit=` filters. Response shape:
  `{ "count": N, "total": M, "risk_factors": [ ...documents... ] }`.
- `/api/status` gains `mongo_connected` and `risk_factor_count` so you can
  confirm it loaded.

### Environment variables (all three required to enable Mongo)

| Variable | Example |
|----------|---------|
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority` |
| `MONGODB_DB` | your database name |
| `MONGODB_COLLECTION` | your collection name |

### Set them on Cloud Run

**GUI:** Cloud Run → `saferoute-api` → **Edit & deploy new revision** →
**Variables & Secrets** → add the three → **Deploy**.

**CLI** (use Secret Manager for the URI so the password isn't in shell history):

```bash
# Store the URI as a secret once:
printf '%s' 'mongodb+srv://user:pass@cluster.mongodb.net/...' \
  | gcloud secrets create mongodb-uri --data-file=-

gcloud run services update saferoute-api --region asia-south1 \
  --set-secrets 'MONGODB_URI=mongodb-uri:latest' \
  --set-env-vars 'MONGODB_DB=your_db,MONGODB_COLLECTION=your_collection'
```

Grant Cloud Run access to the secret if prompted:

```bash
gcloud secrets add-iam-policy-binding mongodb-uri \
  --member="serviceAccount:$(gcloud run services describe saferoute-api \
     --region asia-south1 --format='value(spec.template.spec.serviceAccountName)')" \
  --role='roles/secretmanager.secretAccessor'
```

> **Never commit the connection string.** `.gitignore` already ignores `.env` /
> `.env.local`; keep it there for local dev only.

### Local dev

Set the three vars in your shell before `uvicorn`:

```powershell
$env:MONGODB_URI="mongodb+srv://..."
$env:MONGODB_DB="your_db"
$env:MONGODB_COLLECTION="your_collection"
uvicorn main:app --reload --port 8000
```

Then verify: `http://localhost:8000/api/status` shows `"mongo_connected": true`
with a `risk_factor_count`, and `http://localhost:8000/api/risk-factors?limit=1`
returns one document.

> **Atlas note:** allow the backend's outbound IP in **Atlas → Network Access**.
> For Cloud Run (dynamic egress), the simplest demo setting is `0.0.0.0/0`
> (allow from anywhere); tighten later with a static egress IP / VPC connector.

### Whether this should feed routing

These Mongo points already **feed routing indirectly**: `saferoute_graph_engine.py`
averages their attributes (`road_risk_score`, `congestion_score`, etc.) onto the
graph edges it builds, and the engine's `routing_cost` uses those. The
`/api/risk-factors` endpoint is a separate read layer for the map overlay. If you
want a *different* blend (e.g. weight `crime_score`/`lighting_score` more heavily
in edge cost, or per-mode), tell me the mapping and I'll adjust the generator or
the engine's cost function.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `/api/status` shows `graph_loaded: false` | In `mongo` mode the graph couldn't be built — usually MongoDB is unreachable or the collection is empty. Confirm `MONGODB_URI/DB/COLLECTION` are set on the service, that Atlas **Network Access** allows Cloud Run, and check the Cloud Run logs for the startup error (they print the node/edge counts on success). |
| Frontend shows "Can't reach the backend" | `NEXT_PUBLIC_API_BASE` is wrong/missing, or CORS blocked it. Verify the value has no trailing slash and matches the live Cloud Run URL; check the browser console for a CORS error. |
| `403 Forbidden` when the frontend calls the API | The service wasn't deployed with `--allow-unauthenticated`. Re-run the deploy with that flag (or `gcloud run services add-iam-policy-binding saferoute-api --member=allUsers --role=roles/run.invoker`). |
| Container fails to start / "did not listen on PORT" | Something bound the wrong port. The Dockerfile binds `$PORT`; don't hardcode a port or set `PORT` yourself. |
| First request very slow, then fine | Cold start if `--min-instances 0` — the container boots and reloads the graph. Set `--min-instances 1` to avoid it. |
| `graph_loaded: false` with a MongoDB error in logs | Numeric columns arriving as strings/nulls can misgroup during graph build. The generator runs `fillna(0)` first, but if a whole field is missing from the collection the graph may differ — confirm the collection matches the `central_bangalore_main_cluster` schema. |
| Upload is huge / slow on `gcloud run deploy` | `.gcloudignore` isn't being picked up — confirm it's at the repo root so `node_modules`/`frontend` aren't uploaded. |
| `ModuleNotFoundError: safe_route_engine` | `SAFEROUTE_ENGINE_DIR` doesn't point at the folder containing `safe_route_engine.py`. In the image it's `/app/engine`; don't override it unless you know the path. |
| Changed `NEXT_PUBLIC_API_BASE` but frontend still hits old URL | It's inlined at build time — trigger a Vercel redeploy. |

---

## Cost summary

| Service | Config | Cost |
|---------|--------|------|
| Vercel (frontend) | Hobby | Free |
| Cloud Run (backend) | `--min-instances 0` | Effectively free within the always-free tier (2M requests/mo); scales to zero when idle, cold start on wake |
| Cloud Run (backend) | `--min-instances 1` | ~a few $/mo to keep 1 instance warm (no cold start) — exact cost depends on memory/CPU/region |
| Cloud Build | per build | Free tier covers ~120 build-min/day; deploys are well within it |
| MongoDB (Atlas) | Free (M0) | Free |

A near-free demo is possible with `--min-instances 0` (tradeoff: cold start).
Use `--min-instances 1` when you want it always responsive. Cloud Run bills per
request/CPU-time, so an idle scaled-to-zero service costs essentially nothing.
