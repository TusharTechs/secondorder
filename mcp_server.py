"""SecondOrder MCP server: theory-of-mind memory as tools for any MCP client.

  python mcp_server.py                      # supervisor mode: full read/write tools over a scenario
  SO_AGENT=Shipping python mcp_server.py    # agent mode: read-only, ACL-scoped to Shipping's own mind

Claude Code:  claude mcp add secondorder -- /path/to/.venv/bin/python /path/to/mcp_server.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from secondorder import tools  # noqa: E402
from secondorder.agent_view import AgentView  # noqa: E402
from secondorder.engine import Scenario  # noqa: E402

SID = os.getenv("SO_SCENARIO", "support")
AGENT = os.getenv("SO_AGENT")
mcp = MCPServer("secondorder", instructions="Theory-of-mind memory: what each agent believes and what it thinks others believe, stored in FalkorDB.")


if AGENT:
    view = AgentView(SID, AGENT)

    @mcp.tool()
    def my_beliefs() -> dict:
        """Everything I currently believe (entity -> value, with how I learned it)."""
        out = {}
        for e in view.entities():
            v, meta = view.resolve([AGENT], e)
            if v is not None:
                out[e] = {"value": v, **(meta or {})}
        return out

    @mcp.tool()
    def what_does_person_believe(person: str, entity: str) -> dict:
        """My model of what `person` believes about `entity` (theory of mind)."""
        v, meta = view.resolve([AGENT, person], entity)
        return {"person": person, "entity": entity, "believes": v, "how_i_know": meta}

    @mcp.tool()
    def nested_belief(chain: list[str], entity: str) -> dict:
        """What I think chain[0] thinks chain[1] thinks ... about entity. Example: ["Maya", "Billing"]."""
        v, meta = view.resolve([AGENT] + chain, entity)
        return {"chain": [AGENT] + chain, "entity": entity, "believes": v, "how_i_know": meta}

    @mcp.tool()
    def who_is_misinformed() -> list:
        """People I believe hold a belief different from mine."""
        return view.misinformed()

else:
    @mcp.tool()
    def believes(chain: list[str], entity: str) -> dict:
        """What chain[0] thinks chain[1] thinks ... about entity. [] = ground truth. Includes provenance."""
        return tools.believes(SID, chain, entity)

    @mcp.tool()
    def false_beliefs(depth: int = 2) -> list:
        """Everyone acting on stale information (depth 1) and every wrong model of another person (depth 2)."""
        return tools.false_beliefs(SID, depth=depth)

    @mcp.tool()
    def handoff_delta(sender: str, receiver: str, about: str = "") -> dict:
        """Minimum context the sender must pass to the receiver (optionally only entities containing `about`)."""
        return tools.handoff_delta(SID, sender, receiver, about=about or None)

    @mcp.tool()
    def who_knows(entity: str) -> dict:
        """Who is up to date and who is out of the loop about an entity."""
        return tools.who_knows(SID, entity)

    @mcp.tool()
    def common_ground(a: str, b: str) -> dict:
        """Facts both believe and each believes the other believes."""
        return tools.common_ground(SID, a, b)

    @mcp.tool()
    def explain(chain: list[str], entity: str) -> dict:
        """Why a perspective believes what it does (source event, witnesses, inheritance, who-told-whom path)."""
        return tools.explain(SID, chain, entity)

    @mcp.tool()
    def plan_announcements(entity: str, speaker: str) -> dict:
        """Compare private messages vs one announcement (simulated on GRAPH.COPY forks) to fix everyone's beliefs."""
        return tools.plan_announcements(SID, entity, speaker)

    @mcp.tool()
    def record(kind: str, room: str = "", agents: list[str] | None = None, speaker: str = "", listener: str = "",
               about: str = "", entity: str = "", value: str = "", text: str = "") -> dict:
        """Write an event into memory. kind: enter(agents, room) | exit(speaker) | state(room, entity, value: a
        change everyone present sees) | say(speaker, room, entity, value) | tell(speaker, listener, entity, value:
        private) | report(speaker, room, about, entity, value: 'about' believes entity=value)."""
        sc = Scenario.load(SID)
        if not sc.agents and not agents:
            sc = Scenario(SID, depth=3, trust="credulous")
        if kind == "enter":
            t = sc.enter(agents or [], room, text=text or None)
        elif kind == "exit":
            t = sc.exit(speaker, text=text or None)
        elif kind == "state":
            t = sc.say(speaker or "system", room, entity, value, text=text or None, changes_world=True)
        elif kind == "say":
            t = sc.say(speaker, room, entity, value, text=text or None)
        elif kind == "tell":
            t = sc.tell(speaker, listener, entity, value, text=text or None)
        elif kind == "report":
            t = sc.report(speaker, room, about, entity, value, text=text or None)
        else:
            return {"error": f"unknown kind {kind}"}
        return {"ok": True, "step": t, "stats": sc.stats()}


if __name__ == "__main__":
    mcp.run()
