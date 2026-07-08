# SafeRoute-AI backend image.
#
# IMPORTANT: build this with the *repository root* as the build context, e.g.
#     docker build -t saferoute-api -f Dockerfile .
# because it bundles three things that live in different top-level folders:
#   - the FastAPI wrapper   (Frontend/saferoute-ai/backend)
#   - the routing engine    (Engine/safe_route_engine.py)
#   - the graph datasets     (Datasets/Edges - Weights/*.csv)
#
# numpy / pandas / scipy all ship manylinux wheels, so python:slim needs no
# compiler toolchain.

FROM python:3.11-slim

WORKDIR /app

# Install Python deps first so this layer is cached across code changes.
COPY Frontend/saferoute-ai/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code, engine, and data. The dataset folder has a space in its name, so
# use the JSON (exec) form of COPY and rename it to a space-free path.
COPY Frontend/saferoute-ai/backend/ ./backend/
COPY Engine/ ./engine/
COPY ["Datasets/Edges - Weights/", "./data/"]

# Point the engine + wrapper at the bundled locations. (main.py inserts
# SAFEROUTE_ENGINE_DIR onto sys.path, then the engine reads SAFEROUTE_DATA_DIR.)
ENV SAFEROUTE_ENGINE_DIR=/app/engine \
    SAFEROUTE_DATA_DIR=/app/data \
    SAFEROUTE_OUTPUT_DIR=/tmp/routes \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Hosts (Render/Railway/Fly) inject $PORT; default to 8000 for local runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
