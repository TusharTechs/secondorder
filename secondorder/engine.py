"""SecondOrder engine: nested belief memory stored in FalkorDB.

Graph layout (one FalkorDB instance, many graphs):

  so:<sid>:world          ground truth: agents, rooms, entities, values, events, who witnessed what
  so:<sid>:mind:<agent>   everything <agent> believes, including nested perspectives:
                          (:Perspective {chain:'alice'})              what Alice believes
                          (:Perspective {chain:'alice>bob'})          what Alice thinks Bob believes
                          (:Perspective {chain:'alice>bob>carol'})    ... up to `depth`
                          (child)-[:INHERITS]->(parent)
                          (:Perspective)-[:BELIEVES {entity, active, t, via, event, src}]->(:Value)

A perspective stores only the beliefs where it *diverges* from its parent. Resolving
"what does alice>bob>carol think X is" walks INHERITS edges up to the nearest perspective
that holds an active belief about X (one Cypher query). When an event updates a perspective,
children that did NOT witness it are first materialised with the old value (copy-on-write
per belief edge), so they keep believing what they believed before.

One graph per agent is the security boundary: a FalkorDB/Redis ACL user for agent Alice is
granted only `so:*:mind:alice` keys, so an agent can never read another agent's private mind,
only its own model of it.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .db import conn, get_db

SEP = ">"
UNKNOWN = "(unknown)"


def chain_key(chain: Iterable[str]) -> str:
    return SEP.join(chain)


def world_key(sid: str) -> str:
    return f"so:{sid}:world"


def mind_key(sid: str, agent: str) -> str:
    return f"so:{sid}:mind:{agent}"


# ----------------------------------------------------------------------------- Cypher
# Every query the product depends on lives here, so the README can list them verbatim.

Q = {
    # ---------------- world graph
    "meta_get": "MATCH (m:Meta) RETURN m.seq, m.chapter, m.room, m.agents, m.depth, m.trust",
    "meta_set": (
        "MERGE (m:Meta {id: 0}) SET m.seq = $seq, m.chapter = $chapter, m.room = $room, "
        "m.agents = $agents, m.depth = $depth, m.trust = $trust"
    ),
    "present": "MATCH (a:Agent)-[:IN]->(:Room {name: $room}) RETURN a.name ORDER BY a.name",
    "where_is": "MATCH (a:Agent {name: $agent})-[:IN]->(r:Room) RETURN r.name",
    "enter": (
        "UNWIND $agents AS name "
        "MERGE (a:Agent {name: name}) MERGE (r:Room {name: $room}) "
        "CREATE (a)-[:IN {since: $t, chapter: $chapter}]->(r)"
    ),
    "exit": (
        "MATCH (a:Agent {name: $agent})-[i:IN]->(r:Room) DELETE i "
        "CREATE (a)-[:EXITED {t: $t, chapter: $chapter}]->(r) RETURN r.name"
    ),
    "event": (
        "CREATE (ev:Event {seq: $t, kind: $kind, text: $text, room: $room, actor: $actor, "
        "entity: $entity, value: $value, chapter: $chapter}) "
        "WITH ev UNWIND $witnesses AS w MERGE (a:Agent {name: w}) CREATE (a)-[:WITNESSED]->(ev)"
    ),
    "event_links": (
        "MATCH (ev:Event {seq: $t}) "
        "OPTIONAL MATCH (actor:Agent {name: $actor}) "
        "FOREACH (_ IN CASE WHEN actor IS NULL THEN [] ELSE [1] END | CREATE (actor)-[:PERFORMED]->(ev)) "
        "WITH ev "
        "OPTIONAL MATCH (e:Entity {name: $entity}) "
        "FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END | CREATE (ev)-[:ABOUT]->(e))"
    ),
    "set_state": (
        "MERGE (e:Entity {name: $entity}) "
        "WITH e OPTIONAL MATCH (e)-[old:IS]->() DELETE old "
        "WITH e MERGE (v:Value {name: $value}) CREATE (e)-[:IS {t: $t}]->(v) "
        "WITH v WHERE $room IS NOT NULL MERGE (r:Room {name: $room}) MERGE (v)-[:LOCATED_IN]->(r)"
    ),
    "visible_in_room": (
        "MATCH (e:Entity)-[:IS]->(v:Value)-[:LOCATED_IN]->(:Room {name: $room}) RETURN e.name, v.name"
    ),
    "truth": "MATCH (e:Entity {name: $entity})-[:IS]->(v:Value) RETURN v.name",
    "entities": "MATCH (e:Entity) RETURN e.name ORDER BY e.name",
    # Hi-ToM trust rule as a graph predicate: a listener trusts a speaker who left the room
    # after them (the speaker saw more), or if the listener was never in the room.
    "trusts": (
        "MATCH (s:Agent {name: $speaker}) "
        "OPTIONAL MATCH (s)-[es:EXITED {chapter: $chapter}]->() "
        "OPTIONAL MATCH (:Agent {name: $listener})-[el:EXITED {chapter: $chapter}]->() "
        "RETURN el IS NULL OR (es IS NOT NULL AND es.t > el.t)"
    ),
    "told": (
        "MERGE (s:Agent {name: $speaker}) MERGE (l:Agent {name: $listener}) "
        "CREATE (s)-[:TOLD {t: $t, entity: $entity, value: $value, public: $public, trusted: $trusted}]->(l)"
    ),
    "missed_events": (
        "MATCH (ev:Event)-[:ABOUT]->(:Entity {name: $entity}) "
        "WHERE ev.kind IN ['observe', 'move'] AND ev.seq > $since "
        "AND NOT (:Agent {name: $agent})-[:WITNESSED]->(ev) "
        "RETURN ev.seq, ev.text, ev.actor, ev.room ORDER BY ev.seq DESC LIMIT 1"
    ),
    "event_by_seq": (
        "MATCH (ev:Event {seq: $t}) OPTIONAL MATCH (w:Agent)-[:WITNESSED]->(ev) "
        "RETURN ev.seq, ev.kind, ev.text, ev.room, collect(w.name)"
    ),
    "timeline": (
        "MATCH (ev:Event) OPTIONAL MATCH (w:Agent)-[:WITNESSED]->(ev) "
        "RETURN ev.seq, ev.kind, ev.text, ev.room, ev.actor, ev.entity, ev.value, collect(w.name) "
        "ORDER BY ev.seq"
    ),
    # Information-flow path through TOLD edges (who told whom), via FalkorDB's shortest-path algorithm.
    "info_path": (
        "MATCH (s:Agent {name: $src}), (d:Agent {name: $dst}) "
        "CALL algo.SPpaths({sourceNode: s, targetNode: d, relTypes: ['TOLD'], pathCount: 1, maxLen: 6}) "
        "YIELD path RETURN [n IN nodes(path) | n.name]"
    ),
    # ---------------- mind graphs
    "ensure_perspectives": (
        "UNWIND $nodes AS n MERGE (p:Perspective {chain: n.chain}) "
        "ON CREATE SET p.depth = n.depth, p.agents = n.agents, p.owner = $owner, p.created = $t"
    ),
    "ensure_inherits": (
        "UNWIND $links AS l MATCH (c:Perspective {chain: l.c}), (p:Perspective {chain: l.p}) "
        "MERGE (c)-[:INHERITS]->(p)"
    ),
    # copy-on-write: freeze the current (inherited) belief of perspectives that did not witness the event
    "materialise": (
        "UNWIND $chains AS ch MATCH (p:Perspective {chain: ch}) "
        "WHERE NOT (p)-[:BELIEVES {entity: $entity, active: true}]->() "
        "OPTIONAL MATCH path = (p)-[:INHERITS*1..6]->(q:Perspective)-[b:BELIEVES {entity: $entity, active: true}]->(v:Value) "
        "WITH p, q, b, v, length(path) AS d ORDER BY d ASC "
        "WITH p, collect([v.name, b.via, b.event, b.src, q.chain])[0] AS best "
        "WITH p, CASE WHEN best[0] IS NULL THEN [$unknown, 'unknown', null, null, null] ELSE best END AS best "
        "MERGE (v2:Value {name: best[0]}) "
        "CREATE (p)-[:BELIEVES {entity: $entity, active: true, t: $t, via: 'retained', orig_via: best[1], "
        "event: best[2], src: best[3], from_chain: best[4]}]->(v2) "
        "RETURN count(p)"
    ),
    "update": (
        "UNWIND $chains AS ch MATCH (p:Perspective {chain: ch}) "
        "OPTIONAL MATCH (p)-[old:BELIEVES {entity: $entity, active: true}]->() "
        "SET old.active = false, old.until = $t "
        "WITH DISTINCT p MERGE (v:Value {name: $value}) "
        "CREATE (p)-[:BELIEVES {entity: $entity, active: true, t: $t, via: $via, event: $event, src: $src}]->(v) "
        "RETURN count(p)"
    ),
    # resolve a nested belief: nearest perspective on the INHERITS path that holds an active belief
    "resolve": (
        "MATCH (p:Perspective) WHERE p.chain IN $prefixes "
        "WITH p ORDER BY p.depth DESC LIMIT 1 "
        "MATCH path = (p)-[:INHERITS*0..6]->(q:Perspective)-[b:BELIEVES {entity: $entity, active: true}]->(v:Value) "
        "RETURN v.name, b.via, b.t, b.event, b.src, q.chain, length(path), b.orig_via, b.from_chain "
        "ORDER BY length(path) ASC LIMIT 1"
    ),
    # time travel: what did this perspective believe at step $at
    "resolve_at": (
        "MATCH (p:Perspective) WHERE p.chain IN $prefixes AND p.created <= $at "
        "WITH p ORDER BY p.depth DESC LIMIT 1 "
        "MATCH path = (p)-[:INHERITS*0..6]->(q:Perspective)-[b:BELIEVES {entity: $entity}]->(v:Value) "
        "WHERE b.t <= $at AND (b.until IS NULL OR b.until > $at) "
        "RETURN v.name, b.via, b.t, b.event, b.src, q.chain, length(path), b.orig_via, b.from_chain "
        "ORDER BY length(path) ASC LIMIT 1"
    ),
    "mind_stats": (
        "MATCH (p:Perspective) OPTIONAL MATCH (p)-[b:BELIEVES]->() "
        "RETURN count(DISTINCT p), count(b), sum(CASE WHEN b.active THEN 1 ELSE 0 END)"
    ),
    "perspectives": (
        "MATCH (p:Perspective) OPTIONAL MATCH (p)-[b:BELIEVES {active: true}]->(v:Value) "
        "RETURN p.chain, p.depth, collect([b.entity, v.name, b.via, b.t]) ORDER BY p.depth, p.chain"
    ),
}


@dataclass
class Belief:
    value: Optional[str]
    via: Optional[str] = None
    t: Optional[int] = None
    event: Optional[int] = None
    src: Optional[str] = None
    held_by: Optional[str] = None  # perspective that actually stores the belief edge
    inherited_hops: int = 0
    orig_via: Optional[str] = None
    from_chain: Optional[str] = None

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class Scenario:
    sid: str
    depth: int = 4
    trust: str = "hitom"  # 'hitom' (exit-order rule) | 'credulous' (listeners believe what they are told)
    agents: list = field(default_factory=list)
    seq: int = 0
    chapter: int = 0
    room: Optional[str] = None
    quiet_rooms: tuple = ("waiting_room",)
    index: bool = True
    _known: dict = field(default_factory=dict)  # owner -> set of perspective chains already merged

    # ------------------------------------------------------------------ plumbing
    @property
    def world(self):
        return get_db().select_graph(world_key(self.sid))

    def mind(self, agent: str):
        return get_db().select_graph(mind_key(self.sid, agent))

    @classmethod
    def load(cls, sid: str) -> "Scenario":
        s = cls(sid)
        try:
            rows = s.world.query(Q["meta_get"]).result_set
        except Exception:
            rows = []
        if rows:
            seq, chapter, room, agents, depth, trust = rows[0]
            s.seq, s.chapter, s.room = seq, chapter, room
            s.agents, s.depth, s.trust = list(agents or []), depth, trust
        return s

    def save(self):
        self.world.query(Q["meta_set"], dict(seq=self.seq, chapter=self.chapter, room=self.room,
                                             agents=self.agents, depth=self.depth, trust=self.trust))

    def keys(self) -> list[str]:
        return [world_key(self.sid)] + [mind_key(self.sid, a) for a in self.agents]

    def delete(self):
        c = conn()
        for k in self.keys():
            try:
                c.execute_command("GRAPH.DELETE", k)
            except Exception:
                pass

    def fork(self, new_sid: str) -> "Scenario":
        """What-if branch: GRAPH.COPY every graph of this scenario under a new id."""
        c = conn()
        for k in self.keys():
            c.execute_command("GRAPH.COPY", k, k.replace(f"so:{self.sid}:", f"so:{new_sid}:", 1))
        s = Scenario.load(new_sid)
        return s

    def _register(self, *names):
        for n in names:
            if n and n not in self.agents:
                self.agents.append(n)

    def _tick(self) -> int:
        self.seq += 1
        return self.seq

    # ------------------------------------------------------------------ world queries
    def present(self, room: str) -> list[str]:
        return [r[0] for r in self.world.query(Q["present"], {"room": room}).result_set]

    def room_of(self, agent: str) -> Optional[str]:
        rs = self.world.query(Q["where_is"], {"agent": agent}).result_set
        return rs[0][0] if rs else None

    def truth(self, entity: str) -> Optional[str]:
        rs = self.world.query(Q["truth"], {"entity": entity}).result_set
        return rs[0][0] if rs else None

    def entities(self) -> list[str]:
        return [r[0] for r in self.world.query(Q["entities"]).result_set]

    def _record(self, kind, text, room=None, actor=None, entity=None, value=None, witnesses=()):
        t = self._tick()
        self.world.query(Q["event"], dict(t=t, kind=kind, text=text, room=room, actor=actor, entity=entity,
                                          value=value, chapter=self.chapter, witnesses=list(witnesses)))
        if actor or entity:
            self.world.query(Q["event_links"], dict(t=t, actor=actor, entity=entity))
        return t

    # ------------------------------------------------------------------ belief writes
    def _chains_among(self, group: list[str]) -> list[tuple]:
        """All perspective chains made only of agents in `group` (distinct members, length <= depth)."""
        out = []
        for k in range(1, min(self.depth, len(group)) + 1):
            out.extend(itertools.permutations(group, k))
        return out

    def _apply(self, entity: str, updates: dict, t: int):
        """updates: chain(tuple) -> (value, via, src). Applies copy-on-write per root agent graph."""
        by_root: dict[str, dict] = {}
        for ch, upd in updates.items():
            by_root.setdefault(ch[0], {})[ch] = upd
        for root, ups in by_root.items():
            U = set(ups)
            M = set()
            for ch in U:
                if len(ch) >= self.depth:
                    continue
                for x in self.agents:
                    if x in ch:
                        continue
                    child = ch + (x,)
                    if child not in U:
                        M.add(child)
            needed = set()
            for ch in U | M:
                for k in range(1, len(ch) + 1):
                    needed.add(ch[:k])
            if root not in self._known and self.index:
                try:  # one range index per mind graph: perspective lookup by chain is the hot path
                    self.mind(root).query("CREATE INDEX FOR (p:Perspective) ON (p.chain)")
                except Exception:
                    pass  # already exists
            known = self._known.setdefault(root, set())
            new = sorted(needed - known, key=len)
            g = self.mind(root)
            if new:
                g.query(Q["ensure_perspectives"], dict(owner=root, t=t, nodes=[
                    {"chain": chain_key(c), "depth": len(c), "agents": list(c)} for c in new]))
                links = [{"c": chain_key(c), "p": chain_key(c[:-1])} for c in new if len(c) > 1]
                if links:
                    g.query(Q["ensure_inherits"], {"links": links})
                known.update(new)
            if M:
                g.query(Q["materialise"], dict(entity=entity, t=t, unknown=UNKNOWN,
                                               chains=[chain_key(c) for c in sorted(M, key=len)]))
            groups: dict[tuple, list] = {}
            for ch, (value, via, src) in ups.items():
                groups.setdefault((value, via, src), []).append(chain_key(ch))
            for (value, via, src), chains in groups.items():
                g.query(Q["update"], dict(entity=entity, value=value, via=via, src=src, event=t, t=t, chains=chains))

    # ------------------------------------------------------------------ events
    def enter(self, agents: list[str], room: str, text: Optional[str] = None):
        self._register(*agents)
        if room not in self.quiet_rooms:
            self.chapter += 1
            self.room = room
        t = self._record("enter", text or f"{', '.join(agents)} entered the {room}.", room=room,
                         witnesses=sorted(set(self.present(room)) | set(agents)))
        self.world.query(Q["enter"], dict(agents=agents, room=room, t=t, chapter=self.chapter))
        if room not in self.quiet_rooms:
            # entrants see where everything in the room is (only the entrants, as in Hi-ToM)
            for entity, value in self.world.query(Q["visible_in_room"], {"room": room}).result_set:
                self._apply(entity, {c: (value, "witnessed", None) for c in self._chains_among(agents)}, t)
        self.save()
        return t

    def exit(self, agent: str, text: Optional[str] = None):
        room = self.room_of(agent)
        t = self._record("exit", text or f"{agent} exited the {room}.", room=room, actor=agent,
                         witnesses=self.present(room) if room else [agent])
        self.world.query(Q["exit"], dict(agent=agent, t=t, chapter=self.chapter))
        self.save()
        return t

    def observe(self, entity: str, value: str, room: Optional[str] = None, actor: Optional[str] = None,
                text: Optional[str] = None, kind: str = "observe", witnesses: Optional[list] = None,
                located: bool = True, order: Optional[list] = None):
        """A state change (or a state everyone present can see). Everyone present witnesses it,
        and every nested perspective made only of witnesses is updated."""
        room = room or (self.room_of(actor) if actor else None) or self.room
        W = witnesses if witnesses is not None else self.present(room)
        if actor and actor not in W:
            W = W + [actor]
        self._register(actor, *W)
        self.world.query(Q["set_state"], dict(entity=entity, value=value, t=self.seq + 1,
                                              room=room if located else None))
        t = self._record(kind, text or f"{actor or 'Someone'} set {entity} to {value}.", room=room, actor=actor,
                         entity=entity, value=value, witnesses=W)
        ups = {c: (value, "witnessed", actor) for c in self._chains_among(W)}
        if order:
            # Replication of the Hi-ToM generator *before* commit 9117f35d ("fix permutation bug"):
            # nested beliefs were only written for observers in list order (itertools.combinations).
            # The released Hi-ToM JSON was generated this way. Not used by the product.
            pos = {a: i for i, a in enumerate(order)}
            ups = {c: u for c, u in ups.items()
                   if len(c) == 1 or all(pos.get(c[i], -1) < pos.get(c[i + 1], -1) for i in range(len(c) - 1))}
        self._apply(entity, ups, t)
        self.save()
        return t

    def move(self, actor: str, entity: str, value: str, text: Optional[str] = None, order: Optional[list] = None):
        return self.observe(entity, value, actor=actor, text=text or f"{actor} moved the {entity} to the {value}.",
                            kind="move", order=order)

    def say(self, speaker: str, room: str, entity: str, value: str, text: Optional[str] = None,
            changes_world: bool = False):
        """A message in a shared channel: becomes common knowledge among everyone present."""
        if changes_world:
            return self.observe(entity, value, room=room, actor=speaker, text=text, kind="observe", located=False)
        W = self.present(room)
        self._register(speaker, *W)
        t = self._record("claim", text or f"{speaker} said in {room} that {entity} is {value}.", room=room,
                         actor=speaker, entity=entity, value=value, witnesses=W)
        for l in W:
            if l != speaker:
                self.world.query(Q["told"], dict(speaker=speaker, listener=l, t=t, entity=entity, value=value,
                                                 public=True, trusted=True))
        self._apply(entity, {c: (value, "told", speaker) for c in self._chains_among(W)}, t)
        self.save()
        return t

    def trusts(self, listener: str, speaker: str) -> bool:
        if self.trust == "credulous":
            return True
        rs = self.world.query(Q["trusts"], dict(speaker=speaker, listener=listener, chapter=self.chapter)).result_set
        return bool(rs and rs[0][0])

    def tell(self, speaker: str, listener: str, entity: str, value: str, text: Optional[str] = None):
        """Private message. Only the listener hears it; whether they believe it is decided by the trust rule."""
        self._register(speaker, listener)
        trusted = self.trusts(listener, speaker)
        t = self._record("tell", text or f"{speaker} privately told {listener} that the {entity} is in the {value}.",
                         room=None, actor=speaker, entity=entity, value=value, witnesses=[speaker, listener])
        self.world.query(Q["told"], dict(speaker=speaker, listener=listener, t=t, entity=entity, value=value,
                                         public=False, trusted=trusted))
        ups = {(speaker, listener): (value, "assumed-trusted", speaker)}
        if trusted:
            ups[(listener,)] = (value, "told", speaker)
            ups[(listener, speaker)] = (value, "told", speaker)
        self._apply(entity, ups, t)
        self.save()
        return t

    def claim(self, speaker: str, entity: str, value: str, listeners: Optional[list] = None,
              text: Optional[str] = None):
        """Public claim heard by everyone (Hi-ToM: all agents). Believers update; the speaker assumes everyone did."""
        self._register(speaker)
        L = [a for a in (listeners or self.agents) if a != speaker]
        believers = [l for l in L if self.trusts(l, speaker)]
        t = self._record("claim", text or f"{speaker} publicly claimed that {entity} is in the {value}.",
                         actor=speaker, entity=entity, value=value, witnesses=[speaker] + L)
        for l in L:
            self.world.query(Q["told"], dict(speaker=speaker, listener=l, t=t, entity=entity, value=value,
                                             public=True, trusted=l in believers))
        ups = {}
        for b in believers:
            ups[(b,)] = (value, "told", speaker)
            ups[(b, speaker)] = (value, "told", speaker)
        for l in L:
            ups[(speaker, l)] = (value, "assumed-trusted", speaker)
        self._apply(entity, ups, t)
        self.save()
        return t

    def report(self, speaker: str, room: str, about: str, entity: str, value: str, text: Optional[str] = None):
        """Speaker tells everyone present what `about` believes ("I told the customer the refund is approved").
        Everyone present (and everyone's model of everyone present) now models `about` as believing `value`."""
        W = self.present(room)
        self._register(speaker, about, *W)
        t = self._record("report", text or f"{speaker} said in {room} that {about} believes {entity} is {value}.",
                         room=room, actor=speaker, entity=entity, value=value, witnesses=W)
        ups = {}
        for c in self._chains_among(W):
            if about not in c and len(c) < self.depth:
                ups[c + (about,)] = (value, "reported", speaker)
        self._apply(entity, ups, t)
        self.save()
        return t

    def chatter(self, room: str, text: str, actor: Optional[str] = None):
        """Channel traffic that carries no tracked facts (it still costs tokens in a transcript handoff)."""
        t = self._record("chatter", text, room=room, actor=actor, witnesses=self.present(room))
        self.save()
        return t

    def noise(self, text: str):
        return self._record("noise", text)

    # ------------------------------------------------------------------ reads
    def resolve(self, chain: list[str], entity: str, at: Optional[int] = None) -> Belief:
        if not chain:
            return Belief(self.truth(entity), via="world")
        prefixes = [chain_key(chain[:k]) for k in range(1, len(chain) + 1)]
        params = dict(prefixes=prefixes, entity=entity)
        if at is None:
            rs = self.mind(chain[0]).query(Q["resolve"], params).result_set
        else:
            params["at"] = at
            rs = self.mind(chain[0]).query(Q["resolve_at"], params).result_set
        if not rs:
            return Belief(None)
        v, via, t, ev, src, held, hops, orig_via, from_chain = rs[0]
        return Belief(None if v == UNKNOWN else v, via, t, ev, src, held, hops, orig_via, from_chain)

    def event(self, seq: Optional[int]):
        if seq is None:
            return None
        rs = self.world.query(Q["event_by_seq"], {"t": seq}).result_set
        if not rs:
            return None
        s, kind, text, room, witnesses = rs[0]
        return {"seq": s, "kind": kind, "text": text, "room": room, "witnesses": sorted(witnesses)}

    def timeline(self):
        rows = self.world.query(Q["timeline"]).result_set
        return [dict(seq=r[0], kind=r[1], text=r[2], room=r[3], actor=r[4], entity=r[5], value=r[6],
                     witnesses=sorted(r[7])) for r in rows]

    def perspectives(self, agent: str):
        rows = self.mind(agent).query(Q["perspectives"]).result_set
        return [dict(chain=r[0], depth=r[1], beliefs=[dict(entity=b[0], value=b[1], via=b[2], t=b[3])
                                                      for b in r[2] if b[0] is not None]) for r in rows]

    def stats(self):
        out = {"graphs": len(self.keys()), "perspectives": 0, "belief_edges": 0, "active_beliefs": 0}
        for a in self.agents:
            try:
                p, b, act = self.mind(a).query(Q["mind_stats"]).result_set[0]
            except Exception:
                continue
            out["perspectives"] += p or 0
            out["belief_edges"] += b or 0
            out["active_beliefs"] += act or 0
        n = len(self.agents)
        out["possible_perspectives"] = sum(
            len(list(itertools.permutations(range(n), k))) for k in range(1, min(self.depth, n) + 1))
        return out
