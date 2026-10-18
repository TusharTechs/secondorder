"""FalkorDB connection.

Uses a remote FalkorDB (Docker / FalkorDB Cloud) when FALKORDB_HOST is set,
otherwise an embedded FalkorDB via falkordblite so the project runs with no setup.
"""
from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_db():
    host = os.getenv("FALKORDB_HOST")
    if host:
        from falkordb import FalkorDB

        return FalkorDB(
            host=host,
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            username=os.getenv("FALKORDB_USERNAME") or None,
            password=os.getenv("FALKORDB_PASSWORD") or None,
        )
    try:
        from redislite import FalkorDB  # falkordblite (embedded FalkorDB, macOS/Linux)
    except ImportError as e:  # e.g. Windows, where falkordblite has no wheels
        raise RuntimeError(
            "Embedded FalkorDB (falkordblite) is not available on this platform. Start a FalkorDB server instead:\n"
            "    docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest\n"
            "and set FALKORDB_HOST=localhost (or use `docker compose up`, or FalkorDB Cloud).") from e

    path = os.getenv("FALKORDB_LITE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "secondorder.db"))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return FalkorDB(os.path.abspath(path))


def conn():
    """Raw redis connection (for GRAPH.COPY, ACL, key listing)."""
    return get_db().connection
