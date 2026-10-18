"""Independent label check: replay every Hi-ToM story through the benchmark's OWN published Oracle and
action classes (third_party/hitom, unmodified) and compare with (a) the released gold labels and (b) SecondOrder.
No FalkorDB, no LLM. If the authors' current code agrees with SecondOrder where the released labels don't,
those labels are inconsistent with the generator itself.

usage: python -m eval.reference_oracle
"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "third_party", "hitom"))
sys.path.insert(0, os.path.join(HERE, ".."))

import dynamic_actions as DA  # noqa: E402  (Hi-ToM authors' code)
from oracle import Oracle  # noqa: E402  (Hi-ToM authors' code)

from secondorder.hitom import parse_question, parse_story, story_agents  # noqa: E402


def replay(events):
    agents = story_agents(events)
    rooms, objects, containers = set(), set(), set()
    room_of_container, chapter_room = {}, None
    chapters = []  # (room, [event idx])
    for i, e in enumerate(events):
        if e["type"] == "enter":
            rooms.add(e["room"])
            if e["room"] != "waiting_room":
                chapter_room = e["room"]
                chapters.append((chapter_room, i))
        if e.get("entity"):
            objects.add(e["entity"])
        if e.get("value"):
            containers.add(e["value"])
            if e["type"] in ("observe", "move") and chapter_room:
                room_of_container.setdefault(e["value"], chapter_room)
    for c in containers:
        room_of_container.setdefault(c, chapter_room)
    o = Oracle(agents, list(rooms), list(objects), list(containers))
    by_room = collections.defaultdict(list)
    for c, r in room_of_container.items():
        by_room[r].append(c)
    for r in rooms:
        o.set_containers(r, by_room.get(r, []))
    present = set()
    exit_t, participants, t = {}, set(), 0
    for i, e in enumerate(events):
        t += 1
        k = e["type"]
        if k == "enter":
            if e["room"] != "waiting_room":
                exit_t, participants = {}, set(e["agents"])
                # objects are already in their container when the chapter starts (as in the generator)
                for f in events[i + 1:]:
                    if f["type"] == "enter" and f["room"] != "waiting_room":
                        break
                    if f["type"] == "observe" and o.get_object_container(f["entity"]) != f["value"]:
                        o.set_object_container(f["entity"], f["value"])
                present = set(e["agents"])
            DA.EnterAction(o, tuple(e["agents"]) + (e["room"],))
        elif k == "exit":
            exit_t[e["agent"]] = t
            present.discard(e["agent"])
            DA.ExitedAction(o, e["agent"])
        elif k == "observe":
            DA.ObjectLocAction(o, e["entity"], sorted(present))
        elif k == "move":
            others = [a for a in sorted(present) if a != e["agent"]]
            DA.MoveAction(o, (e["agent"], e["entity"], e["value"]), others)
        elif k in ("claim", "tell"):
            s = e["agent"]

            def trusts(listener):
                if listener not in participants:
                    return True
                return s in exit_t and listener in exit_t and exit_t[s] > exit_t[listener]
            if k == "claim":
                listeners = [a for a in agents if a != s]
                DA.PublicTellAction(o, s, e["entity"], e["value"], listeners=listeners,
                                    believers=[l for l in listeners if trusts(l)])
            else:
                DA.PrivateTellAction(o, s, e["listener"], e["entity"], e["value"], trust=trusts(e["listener"]))
    return o


def answer(o, chain, obj):
    if not chain:
        return o.get_object_container(obj)
    f = [o.get_first_belief, o.get_second_belief, o.get_third_belief, o.get_fourth_belief][len(chain) - 1]
    return f(*chain, obj)


def main():
    items = json.load(open(os.path.join(HERE, "..", "data", "hitom.json")))["data"]
    so = {r["idx"]: r for r in json.load(open(os.path.join(HERE, "results", "graph_parsed.json")))}
    rows, c = [], collections.Counter()
    for i, x in enumerate(items):
        ev = parse_story(x["story"])
        chain, obj = parse_question(x["question"])
        try:
            ref = answer(replay(ev), chain, obj)
        except Exception as e:  # noqa: BLE001
            ref = f"ERROR {e!r}"[:80]
        s = so[i]["pred"]
        c[("ref==gold" if ref == x["answer"] else "ref!=gold", "so==ref" if s == ref else "so!=ref")] += 1
        rows.append({"idx": i, "order": x["question_order"], "gold": x["answer"], "reference": ref, "secondorder": s})
    json.dump(rows, open(os.path.join(HERE, "results", "reference_oracle.json"), "w"), indent=0)
    n = len(rows)
    agree_so = sum(r["reference"] == r["secondorder"] for r in rows)
    agree_gold = sum(r["reference"] == r["gold"] for r in rows)
    print(f"Hi-ToM's own Oracle code vs SecondOrder: {agree_so}/{n} agree")
    print(f"Hi-ToM's own Oracle code vs released labels: {agree_gold}/{n} agree")
    print(c)


if __name__ == "__main__":
    main()
