"""The developer-facing API.

    from secondorder import Memory
    mem = Memory("support")                                   # embedded FalkorDB (or Memory("support", host="localhost"))
    mem.join(["Maya", "Billing"], "chat")
    mem.say("Billing", "refund", "approved", room="chat")      # Maya and Billing now both know, and know the other knows
    mem.leave("Maya"); mem.join(["Billing", "Finance"], "ops")
    mem.set("refund", "rejected", room="ops", by="Finance")    # Maya didn't see this
    mem.believes("Maya", "refund")                 # 'approved'  (false belief)
    mem.believes(["Finance", "Maya"], "refund")    # what Finance thinks Maya believes
    mem.context_for("Billing", talking_to="Maya")  # ready-to-prompt block: what Maya knows / doesn't / misbelieves
"""
from __future__ import annotations

import os
from typing import Iterable, Optional, Union

from . import tools
from .engine import Scenario

Chain = Union[str, Iterable[str]]


class Memory:
    def __init__(self, name: str = "default", *, depth: int = 3, trust: str = "credulous",
                 host: Optional[str] = None, port: int = 6379, password: Optional[str] = None, fresh: bool = False):
        if host:
            os.environ["FALKORDB_HOST"], os.environ["FALKORDB_PORT"] = host, str(port)
            if password:
                os.environ["FALKORDB_PASSWORD"] = password
        self.name = name
        sc = Scenario.load(name)
        if fresh or not sc.agents:
            if fresh:
                sc.delete()
            sc = Scenario(name, depth=depth, trust=trust)
        self.sc = sc

    # ------------------------------------------------------------ writes (perception events)
    def join(self, agents: Union[str, list], room: str):
        """Agents enter a room / channel / meeting. They see what is already visible there."""
        agents = [agents] if isinstance(agents, str) else list(agents)
        return self.sc.enter(agents, room)

    def leave(self, agent: str):
        return self.sc.exit(agent)

    def set(self, entity: str, value: str, *, room: str, by: Optional[str] = None, text: Optional[str] = None):
        """The world changes, and everyone present in `room` sees it."""
        if by is None:
            return self.sc.observe(entity, value, room=room, text=text or f"{entity} is now {value}.", located=False)
        return self.sc.say(by, room, entity, value, text=text, changes_world=True)

    def say(self, speaker: str, entity: str, value: str, *, room: str, text: Optional[str] = None):
        """Speaker states something in a room: it becomes common knowledge among everyone present."""
        return self.sc.say(speaker, room, entity, value, text=text)

    def tell(self, speaker: str, listener: str, entity: str, value: str, text: Optional[str] = None):
        """Private message: only the listener hears it."""
        return self.sc.tell(speaker, listener, entity, value, text=text)

    def report(self, speaker: str, about: str, entity: str, value: str, *, room: str, text: Optional[str] = None):
        """Speaker tells the room what `about` believes ("I told Maya her refund is approved")."""
        return self.sc.report(speaker, room, about, entity, value, text=text)

    # ------------------------------------------------------------ reads
    def believes(self, chain: Chain, entity: str, at: Optional[int] = None) -> Optional[str]:
        chain = [chain] if isinstance(chain, str) else list(chain)
        return self.sc.resolve(chain, entity, at=at).value

    def truth(self, entity: str) -> Optional[str]:
        return self.sc.truth(entity)

    def false_beliefs(self, depth: int = 2):
        return tools.false_beliefs(self.name, depth=depth)

    def handoff(self, sender: str, receiver: str, about: Optional[str] = None):
        return tools.handoff_delta(self.name, sender, receiver, about=about)

    def who_knows(self, entity: str):
        return tools.who_knows(self.name, entity)

    def common_ground(self, a: str, b: str):
        return tools.common_ground(self.name, a, b)

    def explain(self, chain: Chain, entity: str):
        chain = [chain] if isinstance(chain, str) else list(chain)
        return tools.explain(self.name, chain, entity)

    def plan_announcement(self, entity: str, speaker: str):
        return tools.plan_announcements(self.name, entity, speaker)

    def context_for(self, agent: str, talking_to: str) -> str:
        """A compact, framework-agnostic context block for `agent`'s next message to `talking_to`, built only from
        `agent`'s own mind (no ground truth): what I believe, what I think they believe, and where we differ."""
        lines = [f"[SecondOrder context for {agent} -> {talking_to}]"]
        for e in self.sc.entities():
            mine = self.sc.resolve([agent], e).value
            theirs = self.sc.resolve([agent, talking_to], e).value
            if mine is None and theirs is None:
                continue
            if theirs is None:
                lines.append(f"- {e}: you believe {mine!r}; {talking_to} has not been told.")
            elif mine != theirs:
                lines.append(f"- {e}: you believe {mine!r}, but {talking_to} believes {theirs!r}. Correct this before relying on it.")
            else:
                lines.append(f"- {e}: {mine!r} (common ground).")
        return "\n".join(lines)

    def stats(self):
        return self.sc.stats()

    def delete(self):
        self.sc.delete()
