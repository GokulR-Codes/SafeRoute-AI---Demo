# Deploying SafeRoute-AI

This guide takes you from the current repo to a live, public URL. It has three
parts you do in order:

1. **Backend** (FastAPI + routing engine) → **Google Cloud Run** (a container).
2. **Frontend** (Next.js) → **Vercel**, pointed at the backend URL.
3. **Database** (Supabase) → optional, slots into the backend later.

```
  Browser ──HTTPS──▶ Vercel (Next.js UI)
                        │  NEXT_PUBLIC_API_BASE
                        ▼
                     Cloud Run (FastAPI  +  safe_route_engine.py  +  CSV datasets)
                        │  (later)
                        ▼
                     Supabase (edge/incident data)
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
| Graph datasets | `Datasets/Edges - Weights/*.csv` (~2.7 MB) | Cloud Run (in Docker image) |
| Web UI | `Frontend/saferoute-ai/frontend/` | Vercel |

> The engine **cannot run on `safe_route_engine.py` alone** — it builds the
> graph from the three CSVs (`graph_nodes.csv`, `graph_edges.csv`,
> `hourly_edge_weights.csv`), so those ship with it. All of the above are
> already committed to the repo (verified), so the host just clones and builds.

> Note: `main.py` imports **`safe_route_engine.py`** — *not*
> `saferoute_graph_engine.py`. The Docker image copies the whole `Engine/`
> folder, so both are present, but only the former is used at runtime.

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

### Environment variables

The Dockerfile already sets sane defaults, so **you don't have to set anything**.
To override, add `--set-env-vars KEY=VALUE` to the deploy command:

| Variable | Default (in image) | Purpose |
|----------|-------------------|---------|
| `SAFEROUTE_ENGINE_DIR` | `/app/engine` | Folder with `safe_route_engine.py` |
| `SAFEROUTE_DATA_DIR` | `/app/data` | Folder with the 3 CSVs |
| `SAFEROUTE_OUTPUT_DIR` | `/tmp/routes` | Where route JSONs are written (ephemeral — `/tmp` is the only writable path on Cloud Run; fine, since the API also returns the data directly) |
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

```bash
# from the repo root
docker build -t saferoute-api -f Dockerfile .
docker run --rm -e PORT=8080 -p 8080:8080 saferoute-api
# then open http://localhost:8080/api/status
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

## Part 4 — Supabase (later, when your friend provides the URL)

Nothing on the frontend talks to Supabase — **only the backend does**. When the
Supabase URL/credentials arrive, the integration point is the engine's data
loading (today it reads local CSVs in `load_graph()` /
`load_area_index()`). Two common approaches:

- **Load at startup from Supabase** instead of CSVs — replace the CSV reads with
  a query, keep everything else identical.
- **Live incidents** — fetch current incidents from Supabase per request and
  pass them into `a_star(..., incidents=...)` (the engine already accepts an
  incidents list).

Pass the Supabase URL + key to the backend as env vars on deploy (e.g.
`--set-env-vars SUPABASE_URL=...,SUPABASE_KEY=...`), or store the key in
[Secret Manager](https://cloud.google.com/run/docs/configuring/services/secrets)
and mount it — never hardcode them. This is a backend-only change; the frontend
and Vercel setup don't change.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `/api/status` shows `graph_loaded: false` | The CSVs weren't found. Confirm `Datasets/Edges - Weights/*.csv` are committed and the Docker build copied them to `/app/data`. Check the Cloud Build logs for the `COPY` step, or the Cloud Run logs for the startup error. |
| Frontend shows "Can't reach the backend" | `NEXT_PUBLIC_API_BASE` is wrong/missing, or CORS blocked it. Verify the value has no trailing slash and matches the live Cloud Run URL; check the browser console for a CORS error. |
| `403 Forbidden` when the frontend calls the API | The service wasn't deployed with `--allow-unauthenticated`. Re-run the deploy with that flag (or `gcloud run services add-iam-policy-binding saferoute-api --member=allUsers --role=roles/run.invoker`). |
| Container fails to start / "did not listen on PORT" | Something bound the wrong port. The Dockerfile binds `$PORT`; don't hardcode a port or set `PORT` yourself. |
| First request very slow, then fine | Cold start if `--min-instances 0` — the container boots and reloads the graph. Set `--min-instances 1` to avoid it. |
| Build fails on `COPY ["Datasets/Edges - Weights/", ...]` | The dataset folder must exist at the repo root with that exact name (it has a space and a hyphen). |
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
| Supabase | Free | Free (provided by your friend) |

A near-free demo is possible with `--min-instances 0` (tradeoff: cold start).
Use `--min-instances 1` when you want it always responsive. Cloud Run bills per
request/CPU-time, so an idle scaled-to-zero service costs essentially nothing.
