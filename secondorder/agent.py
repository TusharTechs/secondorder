"""A live Claude agent that answers a customer using its own (ACL-scoped) SecondOrder memory.

mode='secondorder': the agent can ask what it believes AND what it thinks the customer believes.
mode='flat':        the agent only sees its own facts (a normal agent memory), no model of the customer.
The agent never writes Cypher and never sees ground truth; it drafts a reply plus the facts the reply
communicates, which (after approval) are written back to memory as a message in the chat.
"""
from __future__ import annotations

import json
from typing import Optional

import anthropic

from .agent_view import AgentView
from .llm import OPUS

SYSTEM = """You are {me}, a customer-support agent for an online store, chatting with the customer {customer}.
Use your memory tools before replying. Be brief, warm and accurate (2-4 sentences). Never invent facts that
are not in your memory. When you are ready, call draft_reply exactly once with your message and the list of
facts your message tells the customer (entity + value), then stop."""

TOOLS_COMMON = [
    {"name": "my_facts", "description": "Everything I (this agent) currently believe: entity -> value, with provenance.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "draft_reply", "description": "Submit the reply to the customer and the facts it communicates.",
     "input_schema": {"type": "object", "properties": {
         "message": {"type": "string"},
         "facts": {"type": "array", "items": {"type": "object", "properties": {
             "entity": {"type": "string"}, "value": {"type": "string"}},
             "required": ["entity", "value"], "additionalProperties": False}}},
         "required": ["message", "facts"], "additionalProperties": False}},
]

TOOLS_TOM = [
    {"name": "what_does_person_believe", "description": "My model of what another person believes about an entity "
     "(theory of mind). Returns their believed value as far as I know, and how I know it.",
     "input_schema": {"type": "object", "properties": {"person": {"type": "string"}, "entity": {"type": "string"}},
                      "required": ["person", "entity"], "additionalProperties": False}},
    {"name": "who_is_misinformed", "description": "People I believe hold a belief that differs from mine.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def _facts(view: AgentView):
    out = {}
    for e in view.entities():
        v, meta = view.resolve([view.me], e)
        if v is not None:
            out[e] = {"value": v, **(meta or {})}
    return out


def run(sid: str, me: str, customer: str, incoming: str, mode: str = "secondorder", model: str = OPUS,
        system_extra: str = "") -> dict:
    view = AgentView(sid, me)
    tools = TOOLS_COMMON + (TOOLS_TOM if mode in ("secondorder", "hybrid") else [])
    if mode == "hybrid":  # recommended: inject the ToM context AND expose the tools
        system_extra = system_extra + "\n\n" + context_block(sid, me, customer)
    client = anthropic.Anthropic(max_retries=4)
    messages = [{"role": "user", "content": f"New message from {customer}: \"{incoming}\""}]
    trace, draft, in_tokens = [], None, 0
    for _ in range(8):
        resp = client.beta.messages.create(
            model=model, max_tokens=4000, system=SYSTEM.format(me=me, customer=customer) + system_extra, tools=tools,
            messages=messages, output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        in_tokens += resp.usage.input_tokens
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            break
        results = []
        for u in uses:
            args = u.input if isinstance(u.input, dict) else json.loads(u.input)
            if u.name == "my_facts":
                out = _facts(view)
            elif u.name == "what_does_person_believe":
                v, meta = view.resolve([me, args["person"]], args["entity"])
                out = {"person": args["person"], "entity": args["entity"], "believes": v, "how_i_know": meta}
            elif u.name == "who_is_misinformed":
                out = view.misinformed()
            elif u.name == "draft_reply":
                draft = args
                out = {"ok": True}
            else:
                out = {"error": "unknown tool"}
            trace.append({"tool": u.name, "args": args, "result": out})
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
        if draft:
            break
    return {"mode": mode, "agent": me, "customer": customer, "incoming": incoming, "draft": draft, "trace": trace,
            "input_tokens": in_tokens}


def commit_reply(sid: str, me: str, customer: str, room: str, draft: dict):
    """After human approval, the reply becomes a message in the chat: the customer (and the agent's model of
    the customer) now hold the communicated facts."""
    from .engine import Scenario

    sc = Scenario.load(sid)
    if me not in sc.present(room):
        sc.enter([me, customer], room, text=f"{customer} and {me} are chatting in #{room}.")
    for f in draft.get("facts", []):
        sc.say(me, room, f["entity"], f["value"], text=f"{me}: {draft['message']}" if f is draft["facts"][0] else
               f"({me} also conveyed {f['entity']} = {f['value']})")
    return sc


def context_block(sid: str, me: str, other: str) -> str:
    """SecondOrder context read ONLY from the agent's own mind graph (ACL-scoped): what I believe, what I think
    `other` believes, and where we differ. Inject it into the prompt (no tool call needed)."""
    view = AgentView(sid, me)
    lines = [f"[SecondOrder memory: what {me} knows, and what {me} believes {other} knows]"]
    for e in view.entities():
        mine, _ = view.resolve([me], e)
        theirs, meta = view.resolve([me, other], e)
        if mine is None:
            continue
        if theirs is None:
            lines.append(f"- {e}: {mine!r}. {other} has not been told.")
        elif theirs != mine:
            lines.append(f"- {e}: {mine!r}. {other} still believes {theirs!r} (from {meta.get('from') or 'earlier'}): "
                         f"correct this explicitly.")
        else:
            lines.append(f"- {e}: {mine!r} ({other} knows).")
    return "\n".join(lines)
