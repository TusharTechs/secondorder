"""Hi-ToM (He et al., EMNLP 2023) adapter: story text -> SecondOrder events, question -> perspective chain.

Two front ends produce the same event list:
  * parse_story():   deterministic parser for the benchmark's templated sentences
  * secondorder.extract.llm_events(): Claude reads free text and emits the events (no templates)
"""
from __future__ import annotations

import re
from typing import Optional

NAME = r"[A-Z][a-z]+"
TOK = r"[a-z][a-z_]*"

PATTERNS = [
    ("enter", re.compile(rf"^(?P<agents>{NAME}(?:, {NAME})*(?: and {NAME})?) entered the (?P<room>{TOK})\.$")),
    ("exit", re.compile(rf"^(?P<agent>{NAME}) exited the (?P<room>{TOK})\.$")),
    ("observe", re.compile(rf"^The (?P<entity>{TOK}) is in the (?P<value>{TOK})\.$")),
    ("move", re.compile(rf"^(?P<agent>{NAME}) moved the (?P<entity>{TOK}) to the (?P<value>{TOK})\.$")),
    ("claim", re.compile(rf"^(?P<agent>{NAME}) publicly claimed that (?:the )?(?P<entity>{TOK}) is in the (?P<value>{TOK})(?: now)?\.$")),
    ("tell", re.compile(rf"^(?P<agent>{NAME}) privately told (?P<listener>{NAME}) that (?:the )?(?P<entity>{TOK}) is in the (?P<value>{TOK})(?: now)?\.$")),
]


def split_agents(s: str) -> list[str]:
    return [a.strip() for a in re.split(r", | and ", s) if a.strip()]


def parse_story(story: str) -> list[dict]:
    events = []
    for line in story.split("\n"):
        line = re.sub(r"^\d+\s+", "", line.strip())
        if not line:
            continue
        for kind, rx in PATTERNS:
            m = rx.match(line)
            if not m:
                continue
            d = m.groupdict()
            if kind == "enter":
                events.append({"type": "enter", "agents": split_agents(d["agents"]), "room": d["room"], "text": line})
            elif kind == "exit":
                events.append({"type": "exit", "agent": d["agent"], "room": d["room"], "text": line})
            elif kind == "observe":
                events.append({"type": "observe", "entity": d["entity"], "value": d["value"], "text": line})
            elif kind == "move":
                events.append({"type": "move", "agent": d["agent"], "entity": d["entity"], "value": d["value"], "text": line})
            elif kind == "claim":
                events.append({"type": "claim", "agent": d["agent"], "entity": d["entity"], "value": d["value"], "text": line})
            elif kind == "tell":
                events.append({"type": "tell", "agent": d["agent"], "listener": d["listener"], "entity": d["entity"],
                               "value": d["value"], "text": line})
            break
        else:
            events.append({"type": "noise", "text": line})
    return events


def parse_question(q: str) -> tuple[list[str], str]:
    """'Where does A think B thinks C thinks the carrot is?' -> (['A','B','C'], 'carrot')."""
    m = re.match(r"^Where is the (\S+) really\?$", q.strip())
    if m:
        return [], m.group(1)
    ent = re.search(r"the (\S+) is\?$", q.strip())
    chain = re.findall(rf"({NAME}) (?:really )?thinks?\b", q)
    return chain, ent.group(1) if ent else None


def story_agents(events: list[dict]) -> list[str]:
    seen = []
    for e in events:
        for k in ("agents",):
            for a in e.get(k, []) or []:
                if a not in seen:
                    seen.append(a)
        for k in ("agent", "listener"):
            a = e.get(k)
            if a and a not in seen:
                seen.append(a)
    return seen


def chapter_exit_orders(events: list[dict]) -> list[list[str]]:
    """Exit order of each chapter (a1..an in the Hi-ToM generator)."""
    orders, cur = [], None
    for e in events:
        if e["type"] == "enter" and e["room"] != "waiting_room":
            cur = []
            orders.append(cur)
        elif e["type"] == "exit" and cur is not None:
            cur.append(e["agent"])
    return orders


def run_events(sc, events: list[dict], extra_agents: Optional[list] = None, legacy_labels: bool = False):
    """Feed events into a Scenario. All agents are registered first so copy-on-write covers everyone.

    legacy_labels=True replicates the observer ordering of the generator version that produced the
    released Hi-ToM labels (see engine.observe); it exists only to audit the benchmark."""
    sc._register(*story_agents(events), *(extra_agents or []))
    orders = chapter_exit_orders(events) if legacy_labels else []
    ch = -1
    for e in events:
        if e["type"] == "enter" and e["room"] != "waiting_room":
            ch += 1
        order = orders[ch] if legacy_labels and 0 <= ch < len(orders) else None
        t = e["type"]
        if t == "enter":
            sc.enter(e["agents"], e["room"], text=e.get("text"))
        elif t == "exit":
            sc.exit(e["agent"], text=e.get("text"))
        elif t == "observe":
            sc.observe(e["entity"], e["value"], text=e.get("text"), order=order)
        elif t == "move":
            mv_order = ([a for a in order if a != e["agent"]] + [e["agent"]]) if order else None
            sc.move(e["agent"], e["entity"], e["value"], text=e.get("text"), order=mv_order)
        elif t == "claim":
            sc.claim(e["agent"], e["entity"], e["value"], text=e.get("text"))
        elif t == "tell":
            sc.tell(e["agent"], e["listener"], e["entity"], e["value"], text=e.get("text"))
        else:
            sc.noise(e.get("text", ""))
