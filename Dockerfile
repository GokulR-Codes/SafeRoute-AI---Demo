# SafeRoute-AI backend image.
#
# IMPORTANT: build this with the *repository root* as the build context, e.g.
#     docker build -t saferoute-api -f Dockerfile .
# because it bundles two folders that live at the top level:
#   - the FastAPI wrapper   (Frontend/saferoute-ai/backend)
#   - the routing engines   (Engine/safe_route_engine.py + saferoute_graph_engine.py)
#
# No datasets are shipped. At startup the backend pulls the raw cluster points
# from MongoDB and builds the graph in-memory via saferoute_graph_engine.py
# (SAFEROUTE_GRAPH_SOURCE=mongo). numpy/pandas/scipy ship manylinux wheels, so
# python:slim needs no compiler toolchain.

FROM python:3.11-slim

WORKDIR /app

# Install Python deps first so this layer is cached across code changes.
COPY Frontend/saferoute-ai/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code + engines only. The whole Engine/ folder carries both
# safe_route_engine.py (routing) and saferoute_graph_engine.py (graph builder).
COPY Frontend/saferoute-ai/backend/ ./backend/
COPY Engine/ ./engine/

# Build the graph from MongoDB at startup; write the generated CSVs to /tmp
# (the only writable path on Cloud Run). MONGODB_URI/DB/COLLECTION are supplied
# at deploy time, not baked into the image.
ENV SAFEROUTE_ENGINE_DIR=/app/engine \
    SAFEROUTE_GRAPH_SOURCE=mongo \
    SAFEROUTE_DATA_DIR=/tmp/saferoute_graph \
    SAFEROUTE_OUTPUT_DIR=/tmp/routes \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Hosts (Render/Railway/Fly) inject $PORT; default to 8000 for local runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
