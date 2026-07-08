"""
MongoDB access for the SafeRoute-AI backend.

This is an *optional* layer. The routing engine still builds its graph from the
CSV datasets (the collection here has no edge topology / hourly weights, so it
can't drive A*). What this collection holds is per-location risk-factor data for
Central Bangalore -- lat/lng plus lighting/crime/congestion/etc. scores -- which
we load once at startup and expose read-only over the API.

Configure with three environment variables (all must be set to enable Mongo):

    MONGODB_URI          e.g. mongodb+srv://user:pass@cluster.mongodb.net/...
    MONGODB_DB           database name
    MONGODB_COLLECTION   collection name

If any is missing, the backend runs exactly as before with Mongo disabled.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DB = os.environ.get("MONGODB_DB")
MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION")

_client: Optional[MongoClient] = None


def mongo_configured() -> bool:
    """True only when all three env vars are present."""
    return bool(MONGODB_URI and MONGODB_DB and MONGODB_COLLECTION)


def get_client() -> MongoClient:
    """Lazily create a shared client. Raises if the URI isn't configured."""
    global _client
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not set")
    if _client is None:
        _client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            appname="saferoute-backend",
        )
    return _client


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Make a Mongo document JSON-safe (stringify _id, keep everything else)."""
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def load_risk_factors() -> List[Dict[str, Any]]:
    """
    Fetch every document in the configured collection. Called once at startup;
    raises PyMongoError on connection/query failure so the caller can degrade.
    """
    client = get_client()
    coll = client[MONGODB_DB][MONGODB_COLLECTION]  # type: ignore[index]
    return [_clean(d) for d in coll.find({})]


def filter_risk_factors(
    docs: List[Dict[str, Any]],
    zone: Optional[str] = None,
    source_area: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """In-memory filtering for the read endpoint (case-insensitive matches)."""
    result = docs
    if zone:
        z = zone.strip().lower()
        result = [d for d in result if str(d.get("zone", "")).lower() == z]
    if source_area:
        a = source_area.strip().lower()
        result = [d for d in result if str(d.get("source_area", "")).lower() == a]
    if limit is not None and limit >= 0:
        result = result[:limit]
    return result


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
