"""Agent-facing tools over SecondOrder. Every tool is a fixed, parameterised graph read/write:
the LLM chooses tools and arguments, never writes Cypher."""
from __future__ import annotations

import itertools
import uuid
from typing import Optional

from .engine import Q, Scenario, chain_key


def _sc(sid: str) -> Scenario:
    return Scenario.load(sid)


def _fmt(b):
    return b.to_dict()


def believes(sid: str, chain: list[str], entity: str, at: Optional[int] = None) -> dict:
    """What does chain[0] think chain[1] thinks ... about `entity`? Empty chain = ground truth."""
    sc = _sc(sid)
    b = sc.resolve(chain, entity, at=at)
    out = {"chain": chain, "entity": entity, "belief": b.value, "truth": sc.truth(entity), "provenance": _fmt(b)}
    out["source_event"] = sc.event(b.event)
    out["correct"] = out["belief"] == out["truth"]
    return out


def false_beliefs(sid: str, depth: int = 2, agents: Optional[list] = None) -> list[dict]:
    """Every perspective (up to `depth`) whose belief differs from the world, with the event it missed.
    depth=1: who is wrong about the world. depth=2: who has a wrong model of someone else."""
    sc = _sc(sid)
    agents = agents or sc.agents
    out = []
    for entity in sc.entities():
        truth = sc.truth(entity)
        for k in range(1, depth + 1):
            for chain in itertools.permutations(agents, k):
                b = sc.resolve(list(chain), entity)
                if b.value is None and k == 1 and not any(chain[0] == e for e in []):
                    # never heard of it: only report if the entity has been discussed with them at all
                    continue
                if b.value is not None and b.value != truth:
                    since = b.t or 0
                    missed = sc.world.query(Q["missed_events"], dict(entity=entity, agent=chain[-1], since=since)).result_set
                    out.append({"chain": list(chain), "entity": entity, "believes": b.value, "truth": truth,
                                "since_step": b.t, "learned_via": b.via, "from": b.src,
                                "missed": ({"step": missed[0][0], "text": missed[0][1]} if missed else None),
                                "summary": _sentence(chain, entity, b.value, truth)})
    return out


def _sentence(chain, entity, believed, truth):
    if len(chain) == 1:
        return f"{chain[0]} believes {entity} = {believed}, but it is {truth}."
    who = " thinks ".join(chain[:-1])
    return f"{who} thinks {chain[-1]} believes {entity} = {believed} (truth: {truth})."


def handoff_delta(sid: str, sender: str, receiver: str, about: Optional[str] = None) -> dict:
    """The minimum context `sender` should pass to `receiver`: facts where the sender's own belief differs
    from the sender's model of the receiver. Also verified against the receiver's actual mind."""
    sc = _sc(sid)
    facts = []
    for entity in sc.entities():
        if about and about not in entity:
            continue
        mine = sc.resolve([sender], entity)
        theirs_modelled = sc.resolve([sender, receiver], entity)
        if mine.value is not None and mine.value != theirs_modelled.value:
            actual = sc.resolve([receiver], entity)
            facts.append({"entity": entity, "tell": mine.value, "they_think": theirs_modelled.value,
                          "receiver_actually_believes": actual.value,
                          "needed": actual.value != mine.value,
                          "why": sc.event(mine.event)["text"] if mine.event else None})
        # second-order facts: what sender thinks *others* believe that the receiver doesn't know
        for third in sc.agents:
            if third in (sender, receiver):
                continue
            m3 = sc.resolve([sender, third], entity)
            r3 = sc.resolve([sender, receiver, third], entity)
            truth = sc.truth(entity)
            if m3.value is not None and m3.value != truth and m3.value != r3.value:
                facts.append({"entity": entity, "about": third, "value": m3.value, "tell": f"{third} still believes {entity} = {m3.value}",
                              "they_think": r3.value, "second_order": True, "needed": True,
                              "why": sc.event(m3.event)["text"] if m3.event else None})
    return {"from": sender, "to": receiver, "facts": facts}


def who_knows(sid: str, entity: str) -> dict:
    sc = _sc(sid)
    truth = sc.truth(entity)
    rows = []
    for a in sc.agents:
        b = sc.resolve([a], entity)
        rows.append({"agent": a, "believes": b.value, "up_to_date": b.value == truth, "since_step": b.t, "via": b.via})
    return {"entity": entity, "truth": truth, "agents": rows,
            "out_of_the_loop": [r["agent"] for r in rows if not r["up_to_date"]]}


def common_ground(sid: str, a: str, b: str) -> dict:
    """Facts A and B both believe AND each believes the other believes (Clark & Brennan's common ground)."""
    sc = _sc(sid)
    shared, partial = [], []
    for e in sc.entities():
        vals = {k: sc.resolve(list(k), e).value for k in [(a,), (b,), (a, b), (b, a)]}
        if vals[(a,)] is not None and len(set(vals.values())) == 1:
            shared.append({"entity": e, "value": vals[(a,)]})
        elif vals[(a,)] is not None or vals[(b,)] is not None:
            partial.append({"entity": e, **{"/".join(k): v for k, v in vals.items()}})
    return {"agents": [a, b], "common_ground": shared, "not_common": partial}


def explain(sid: str, chain: list[str], entity: str) -> dict:
    """Why does this perspective believe what it believes? The perspective path, the source event and
    its witnesses, and the information-flow path through TOLD edges."""
    sc = _sc(sid)
    b = sc.resolve(chain, entity)
    steps = []
    if b.held_by and b.held_by != chain_key(chain):
        steps.append(f"'{chain_key(chain)}' has no belief of its own about {entity}; it inherits from "
                     f"'{b.held_by}' ({b.inherited_hops} hop(s) up the perspective tree).")
    ev = sc.event(b.event)
    if b.via == "retained":
        steps.append(f"Frozen at step {b.t}: an event changed {entity} while '{chain[-1]}' (from this perspective) "
                     f"was not there, so this perspective kept its earlier belief from '{b.from_chain}'.")
    if ev:
        steps.append(f"Source event #{ev['seq']}: \"{ev['text']}\" witnessed by {', '.join(ev['witnesses'])}.")
    path = None
    if b.src and b.via in ("told", "reported") and len(chain) >= 1:
        try:
            rs = sc.world.query(Q["info_path"], {"src": b.src, "dst": chain[0]}).result_set
            path = rs[0][0] if rs else None
        except Exception:
            path = None
    return {"chain": chain, "entity": entity, "belief": b.value, "via": b.via, "steps": steps,
            "info_path": path, "provenance": _fmt(b)}


def plan_announcements(sid: str, entity: str, speaker: str, rooms: Optional[dict] = None, commit: bool = False) -> dict:
    """Plan the fewest messages that make everyone's belief AND everyone's model of each other correct.

    Simulates each candidate plan on a GRAPH.COPY fork of the scenario, measures remaining false beliefs
    (depth 2), and returns the plan comparison. Candidates: private tells to each stale agent vs one
    public announcement to everyone stale."""
    sc = _sc(sid)
    truth = sc.truth(entity)
    stale = [a for a in sc.agents if a != speaker and sc.resolve([a], entity).value not in (truth,)]
    plans = {}

    def remaining(fork_sid):
        return [f for f in false_beliefs(fork_sid, depth=2) if f["entity"] == entity]

    # plan A: private tells
    fa = sc.fork(f"{sid}-planA-{uuid.uuid4().hex[:6]}")
    fa.trust = "credulous"
    for a in stale:
        fa.tell(speaker, a, entity, truth, text=f"{speaker} privately told {a} that {entity} is {truth}.")
    plans["private_tells"] = {"messages": len(stale), "remaining_false_beliefs": len(remaining(fa.sid)),
                              "steps": [f"{speaker} -> {a}: {entity} is {truth}" for a in stale]}
    # plan B: one public announcement to everyone stale + speaker
    fb = sc.fork(f"{sid}-planB-{uuid.uuid4().hex[:6]}")
    fb.trust = "credulous"
    room = f"announce-{entity}"
    fb.enter(list(sc.agents), room)
    fb.say(speaker, room, entity, truth)
    plans["public_announcement"] = {"messages": 1 if stale else 0, "remaining_false_beliefs": len(remaining(fb.sid)),
                                    "steps": [f"{speaker} -> #{room} (everyone): {entity} is {truth}"]}
    for f in (fa, fb):
        f.delete()
    best = min(plans, key=lambda k: (plans[k]["remaining_false_beliefs"], plans[k]["messages"]))
    return {"entity": entity, "truth": truth, "stale_agents": stale, "plans": plans, "recommended": best}


def mind_map(sid: str, agent: str) -> list[dict]:
    return _sc(sid).perspectives(agent)


TOOL_SPECS = [
    {"name": "believes", "description": "What a perspective believes about an entity. chain=['Maya'] is Maya's belief; "
     "['Shipping','Maya'] is what Shipping thinks Maya believes; [] is ground truth. Returns provenance.",
     "input_schema": {"type": "object", "properties": {"chain": {"type": "array", "items": {"type": "string"}},
                                                       "entity": {"type": "string"}},
                      "required": ["chain", "entity"], "additionalProperties": False}},
    {"name": "false_beliefs", "description": "List everyone acting on stale information (depth 1) and every wrong "
     "model of another person (depth 2), with the event each perspective missed.",
     "input_schema": {"type": "object", "properties": {"depth": {"type": "integer", "enum": [1, 2]}},
                      "required": ["depth"], "additionalProperties": False}},
    {"name": "handoff_delta", "description": "Minimum context the sender must pass to the receiver: facts the "
     "receiver (as modelled by the sender) does not know, including who else holds a false belief.",
     "input_schema": {"type": "object", "properties": {"sender": {"type": "string"}, "receiver": {"type": "string"}},
                      "required": ["sender", "receiver"], "additionalProperties": False}},
    {"name": "who_knows", "description": "Who is up to date and who is out of the loop about an entity.",
     "input_schema": {"type": "object", "properties": {"entity": {"type": "string"}},
                      "required": ["entity"], "additionalProperties": False}},
    {"name": "explain", "description": "Why a perspective believes what it does: source event, witnesses, "
     "inheritance in the perspective tree and the who-told-whom path.",
     "input_schema": {"type": "object", "properties": {"chain": {"type": "array", "items": {"type": "string"}},
                                                       "entity": {"type": "string"}},
                      "required": ["chain", "entity"], "additionalProperties": False}},
]


def call(sid: str, name: str, args: dict):
    if name == "believes":
        return believes(sid, args["chain"], args["entity"])
    if name == "false_beliefs":
        return false_beliefs(sid, depth=args.get("depth", 2))
    if name == "handoff_delta":
        return handoff_delta(sid, args["sender"], args["receiver"])
    if name == "who_knows":
        return who_knows(sid, args["entity"])
    if name == "explain":
        return explain(sid, args["chain"], args["entity"])
    if name == "common_ground":
        return common_ground(sid, args["a"], args["b"])
    raise ValueError(f"unknown tool {name}")
