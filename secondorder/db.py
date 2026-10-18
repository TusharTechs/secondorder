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
    from redislite import FalkorDB  # falkordblite

    path = os.getenv("FALKORDB_LITE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "secondorder.db"))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return FalkorDB(os.path.abspath(path))


def conn():
    """Raw redis connection (for GRAPH.COPY, ACL, key listing)."""
    return get_db().connection
