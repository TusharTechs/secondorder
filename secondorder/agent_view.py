"""An agent's own, access-controlled view of memory.

Each agent connects to FalkorDB as its own ACL user that may only run read-only graph queries on
`so:*:mind:<agent>`. It can ask what it believes and what it thinks others believe, but it cannot
read the world graph or anyone else's mind (FalkorDB returns NOPERM). Theory of mind, not omniscience.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache

import redis

from .db import conn, get_db
from .engine import Q, UNKNOWN, chain_key, mind_key


_SECRET = os.getenv("SO_ACL_SECRET") or secrets.token_hex(16)  # random per process unless configured


def _password(agent: str) -> str:
    return f"{_SECRET}-{agent}"


def ensure_acl_user(agent: str) -> str:
    user = f"agent_{agent.lower()}"
    conn().execute_command("ACL", "SETUSER", user, "on", f">{_password(agent)}", "resetkeys",
                           f"~so:*:mind:{agent}", "-@all", "+GRAPH.RO_QUERY", "+ping")
    return user


@lru_cache(maxsize=64)
def _agent_conn(agent: str) -> redis.Redis:
    user = ensure_acl_user(agent)
    kw = conn().connection_pool.connection_kwargs
    if kw.get("path"):
        return redis.Redis(unix_socket_path=kw["path"], username=user, password=_password(agent), decode_responses=True)
    return redis.Redis(host=kw.get("host", "localhost"), port=kw.get("port", 6379), username=user,
                       password=_password(agent), decode_responses=True)


def _ro(agent: str, key: str, query: str, params: dict):
    """Run a parameterised read-only query as the agent's ACL user."""
    from falkordb.helpers import quote_string  # noqa: F401  (ensures falkordb installed)
    import json

    def lit(v):
        if v is None:
            return "null"
        if isinstance(v, (list, tuple)):
            return "[" + ", ".join(lit(x) for x in v) + "]"
        if isinstance(v, (int, float)):
            return str(v)
        return json.dumps(str(v), ensure_ascii=False)

    header = "CYPHER " + " ".join(f"{k}={lit(v)}" for k, v in params.items()) + " " if params else ""
    res = _agent_conn(agent).execute_command("GRAPH.RO_QUERY", key, header + query)
    return res[1] if len(res) > 2 else []


class AgentView:
    def __init__(self, sid: str, me: str):
        self.sid, self.me = sid, me
        self.key = mind_key(sid, me)

    def resolve(self, chain: list[str], entity: str):
        if not chain or chain[0] != self.me:
            chain = [self.me] + [c for c in chain if c != self.me]
        prefixes = [chain_key(chain[:k]) for k in range(1, len(chain) + 1)]
        rows = _ro(self.me, self.key, Q["resolve"], {"prefixes": prefixes, "entity": entity})
        if not rows:
            return None, None
        v, via, t, ev, src, held, hops, *_ = rows[0]
        return (None if v == UNKNOWN else v), {"via": via, "step": t, "from": src, "held_by": held}

    def entities(self) -> list[str]:
        rows = _ro(self.me, self.key, "MATCH ()-[b:BELIEVES]->() RETURN DISTINCT b.entity", {})
        return sorted(r[0] for r in rows)

    def agents_modelled(self) -> list[str]:
        rows = _ro(self.me, self.key, "MATCH (p:Perspective) WHERE p.depth = 2 RETURN p.agents[1]", {})
        return sorted({r[0] for r in rows})

    def misinformed(self) -> list[dict]:
        """Who do *I* think holds a belief different from mine? (No access to ground truth.)"""
        out = []
        for e in self.entities():
            mine, _ = self.resolve([self.me], e)
            if mine is None:
                continue
            for other in self.agents_modelled():
                theirs, meta = self.resolve([self.me, other], e)
                if theirs is not None and theirs != mine:
                    out.append({"agent": other, "entity": e, "they_believe": theirs, "i_believe": mine, **(meta or {})})
        return out

    def try_read_other(self, other: str):
        """Demonstrates the boundary: reading another agent's mind is refused by FalkorDB."""
        try:
            _agent_conn(self.me).execute_command("GRAPH.RO_QUERY", mind_key(self.sid, other),
                                                 "MATCH (p:Perspective) RETURN count(p)")
            return "allowed (unexpected)"
        except redis.exceptions.NoPermissionError as e:
            return f"refused by FalkorDB ACL: {e}"
