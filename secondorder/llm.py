"""Claude calls: LLM-only baseline answers and free-text -> event extraction."""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Optional

import anthropic

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-5-5"

_client: Optional[anthropic.AsyncAnthropic] = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(max_retries=6)
    return _client


async def ask(model: str, prompt: str, *, system: Optional[str] = None, effort: str = "medium",
              max_tokens: int = 16000, fmt: Optional[dict] = None) -> tuple[str, dict]:
    """One request; returns (text, usage). Opus requests opt into server-side refusal fallbacks."""
    kw = dict(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
    if system:
        kw["system"] = system
    oc = {"effort": effort}
    if fmt:
        oc["format"] = fmt
    kw["output_config"] = oc
    if model == OPUS:
        resp = await client().beta.messages.create(**kw, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    else:
        resp = await client().messages.create(**kw)
    if resp.stop_reason == "refusal":
        return "", {"refusal": True}
    text = "".join(b.text for b in resp.content if b.type == "text")
    u = resp.usage
    return text, {"in": u.input_tokens, "out": u.output_tokens}


ANSWER_SUFFIX = "\n\nEnd your reply with a final line exactly of the form `Answer: <option text>`."


def parse_answer(text: str, choices: str) -> Optional[str]:
    opts = [c.split(". ", 1)[1].strip() for c in re.split(r",\s*(?=[A-Z]\. )", choices) if ". " in c]
    m = re.findall(r"Answer:\s*`?([A-Za-z_]+(?:\.\s*[a-z_]+)?)", text)
    if m:
        cand = m[-1].strip().rstrip("`.")
        if ". " in cand:
            cand = cand.split(". ", 1)[1]
        if cand in opts:
            return cand
        letter = re.match(r"^([A-Z])$", cand)
        if letter:
            for c in re.split(r",\s*(?=[A-Z]\. )", choices):
                if c.startswith(letter.group(1) + ". "):
                    return c.split(". ", 1)[1].strip()
    # fallback: last option mentioned
    best, pos = None, -1
    for o in opts:
        p = text.rfind(o)
        if p > pos:
            best, pos = o, p
    return best


EVENT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["enter", "exit", "observe", "move", "claim", "tell", "noise"]},
                        "agents": {"type": "array", "items": {"type": "string"}},
                        "agent": {"type": "string"},
                        "listener": {"type": "string"},
                        "room": {"type": "string"},
                        "entity": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["type", "agents", "agent", "listener", "room", "entity", "value"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["events"],
        "additionalProperties": False,
    },
}

EXTRACT_SYSTEM = """You convert a narrative into a list of perception events for a belief-tracking memory.
Emit one event per thing that happens, in story order. Event types:
- enter: people (agents) enter a place (room).
- exit: one person (agent) leaves a place (room).
- observe: everyone currently present can see that a thing (entity) is in/at a place or container (value).
- move: a person (agent) moves a thing (entity) to a container/place (value) - everyone present sees it.
- claim: a person (agent) announces publicly that a thing (entity) is in a container (value).
- tell: a person (agent) privately tells one person (listener) that a thing (entity) is in a container (value).
- noise: anything irrelevant to where things are (likes, dislikes, sightings, waiting without acting).
Use exact names from the text; for multi-word containers/places keep the original token (e.g. green_drawer).
Unused fields are empty strings / empty lists. Do not answer any question; only extract events."""


def normalise_events(evts: list[dict]) -> list[dict]:
    out = []
    for e in evts:
        d = {k: v for k, v in e.items() if v not in ("", [], None)}
        d.setdefault("type", "noise")
        if d["type"] == "enter" and "agents" not in d and "agent" in d:
            d["agents"] = [d.pop("agent")]
        out.append(d)
    return out


async def extract_events(story: str, model: str = OPUS) -> tuple[list[dict], dict]:
    text, usage = await ask(model, f"Story:\n{story.strip()}", system=EXTRACT_SYSTEM, effort="low", fmt=EVENT_SCHEMA)
    data = json.loads(text) if text else {"events": []}
    return normalise_events(data["events"]), usage


async def gather_limited(coros, limit: int = 16):
    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            return await c

    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)
