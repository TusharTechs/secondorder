"""SecondOrder web API + demo UI."""
from __future__ import annotations

import collections
import concurrent.futures
import json
import os
import sys
import time
from functools import lru_cache

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from secondorder import tools  # noqa: E402
from secondorder.agent_view import AgentView  # noqa: E402
from secondorder.engine import Q, Scenario  # noqa: E402
from secondorder.hitom import parse_question, parse_story, run_events  # noqa: E402
from secondorder.scenarios import build_org, build_support, handoff  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATIC = os.path.join(os.path.dirname(__file__), "static")
RESULTS = os.path.join(ROOT, "eval", "results")
LLM_ENABLED = bool(os.getenv("ANTHROPIC_API_KEY")) and os.getenv("SO_DISABLE_LLM") != "1"

app = FastAPI(title="SecondOrder")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


ALLOWED = {"support", "org"}


def _ensure(sid):
    if sid not in ALLOWED:
        raise HTTPException(404, "unknown scenario")
    sc = Scenario.load(sid)
    if not sc.agents:
        if sid == "support":
            build_support()
        elif sid == "org":
            build_org()
        else:
            raise HTTPException(404, "unknown scenario")
        sc = Scenario.load(sid)
    return sc


def _snapshot(sid):
    sc = _ensure(sid)
    minds = {a: sc.perspectives(a) for a in sc.agents}
    ents = sc.entities()
    return {"sid": sid, "agents": sc.agents, "entities": ents, "truth": {e: sc.truth(e) for e in ents},
            "timeline": sc.timeline(), "minds": minds, "stats": sc.stats(),
            "false_beliefs": tools.false_beliefs(sid, depth=2), "llm": LLM_ENABLED}


@app.get("/api/{sid}/state")
def state(sid: str):
    return _snapshot(sid)


@app.post("/api/{sid}/reset")
def reset(sid: str):
    if sid not in ALLOWED:
        raise HTTPException(404, "unknown scenario")
    if sid == "support":
        build_support()
    elif sid == "org":
        build_org()
    return _snapshot(sid)


@app.get("/api/{sid}/believes")
def believes(sid: str, chain: str = "", entity: str = "", at: int | None = None):
    return tools.believes(sid, [c for c in chain.split(",") if c], entity, at=at)


@app.get("/api/{sid}/explain")
def explain(sid: str, chain: str, entity: str):
    return tools.explain(sid, [c for c in chain.split(",") if c], entity)


@app.get("/api/{sid}/who_knows")
def who_knows(sid: str, entity: str):
    return tools.who_knows(sid, entity)


@app.get("/api/{sid}/common_ground")
def common_ground(sid: str, a: str, b: str):
    return tools.common_ground(sid, a, b)


@app.get("/api/{sid}/plan")
def plan(sid: str, entity: str, speaker: str):
    _ensure(sid)
    return tools.plan_announcements(sid, entity, speaker)


@lru_cache(maxsize=256)
def _count_tokens(text: str) -> int:
    if LLM_ENABLED:
        try:
            import anthropic

            r = anthropic.Anthropic().messages.count_tokens(model="claude-opus-5-5",
                                                            messages=[{"role": "user", "content": text}])
            return r.input_tokens
        except Exception:
            pass
    return int(len(text.split()) * 1.35)


@app.get("/api/{sid}/handoff")
def handoff_preview(sid: str, sender: str, receiver: str, about: str = "4411"):
    sc = _ensure(sid)
    d = tools.handoff_delta(sid, sender, receiver, about=about)
    transcript = "\n".join(e["text"] for e in sc.timeline() if sender in e["witnesses"] and e["kind"] != "noise")
    delta_text = "\n".join(f"- {f['tell'] if f.get('second_order') else f['entity'] + ' = ' + f['tell']}"
                           for f in d["facts"])
    d["transcript"] = transcript
    d["delta_text"] = delta_text
    d["tokens"] = {"full_transcript": _count_tokens(transcript or "-"), "delta": _count_tokens(delta_text or "-")}
    return d


class HandoffReq(BaseModel):
    sender: str
    receiver: str


@app.post("/api/{sid}/handoff")
def handoff_commit(sid: str, req: HandoffReq):
    sc = _ensure(sid)
    handoff(sc, req.sender, req.receiver, tools.handoff_delta(sid, req.sender, req.receiver, about="4411"))
    return _snapshot(sid)


@app.get("/api/{sid}/acl")
def acl(sid: str, agent: str, other: str):
    v = AgentView(sid, agent)
    return {"agent": agent, "own_entities": v.entities(), "reading_other": v.try_read_other(other),
            "misinformed": v.misinformed()}


class AgentReq(BaseModel):
    agent: str = "Shipping"
    customer: str = "Maya"
    message: str = Field("Hi! Any update on order #4411?", max_length=400)


CACHE_AGENT = os.path.join(RESULTS, "agent_demo_cache.json")
_RUNS: list[float] = []
MAX_RUNS = int(os.getenv("SO_LIVE_AGENT_RUNS_PER_HOUR", "1000"))


@app.post("/api/{sid}/agent")
def run_agent(sid: str, req: AgentReq):
    from secondorder import agent

    now = time.time()
    _RUNS[:] = [t for t in _RUNS if now - t < 3600]
    if not LLM_ENABLED or len(_RUNS) >= MAX_RUNS:
        if os.path.exists(CACHE_AGENT):
            return json.load(open(CACHE_AGENT)) | {"cached": True}
        raise HTTPException(503, "LLM disabled")
    _RUNS.append(now)
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        futs = {m: ex.submit(agent.run, sid, req.agent, req.customer, req.message, m) for m in ("flat", "secondorder")}
        out = {m: f.result() for m, f in futs.items()}
    if os.getenv("SO_RECORD_AGENT_CACHE") == "1":  # only when deliberately recording the replay
        os.makedirs(RESULTS, exist_ok=True)
        json.dump(out, open(CACHE_AGENT, "w"), indent=1)
    return out


class ApproveReq(BaseModel):
    agent: str
    customer: str
    room: str = "chat-shipping"
    draft: dict


@app.post("/api/{sid}/approve")
def approve(sid: str, req: ApproveReq):
    from secondorder.agent import commit_reply

    commit_reply(sid, req.agent, req.customer, req.room, req.draft)
    return _snapshot(sid)


# ----------------------------------------------------------------------------- Hi-ToM explorer
@lru_cache(maxsize=1)
def _hitom():
    return json.load(open(os.path.join(ROOT, "data", "hitom.json")))["data"]


def _load_results(name):
    p = os.path.join(RESULTS, name)
    return json.load(open(p)) if os.path.exists(p) else None


@app.get("/api/hitom/{idx}")
def hitom_item(idx: int):
    if not 0 <= idx < len(_hitom()):
        raise HTTPException(404, "no such question")
    x = _hitom()[idx]
    sid = f"hitom{idx}"
    sc = Scenario(sid, depth=4, trust="hitom")
    sc.delete()
    sc = Scenario(sid, depth=4, trust="hitom")
    events = parse_story(x["story"])
    t0 = time.perf_counter()
    run_events(sc, events)
    ms = (time.perf_counter() - t0) * 1000
    chain, entity = parse_question(x["question"])
    b = sc.resolve(chain, entity)
    # belief of every prefix of the chain at every step (time travel)
    steps = sc.timeline()
    evolution = []
    for k in range(1, len(chain) + 1):
        row = []
        for ev in steps:
            row.append(sc.resolve(chain[:k], entity, at=ev["seq"]).value)
        evolution.append({"chain": chain[:k], "values": row})
    reasoning = []
    for k in range(1, len(chain) + 1):
        bk = sc.resolve(chain[:k], entity)
        ev = sc.event(bk.event)
        who = " thinks ".join(chain[:k - 1])
        head = (f"{who} thinks {chain[k - 1]} believes" if k > 1 else f"{chain[0]} believes")
        reasoning.append({"chain": chain[:k], "value": bk.value, "via": bk.via,
                          "text": f"{head} the {entity} is in the {bk.value}" + (
                              f": {bk.via} at step {ev['seq']} (“{ev['text']}”, witnessed by {', '.join(ev['witnesses'])})" if ev else "")})
    llm = {}
    for m in ("claude-opus-5-5", "claude-haiku-5-5"):
        r = _load_results(f"llm_{m}.json")
        if r and str(idx) in r:
            llm[m] = {"pred": r[str(idx)]["pred"], "ok": r[str(idx)]["ok"], "text": r[str(idx)].get("text", "")[-400:]}
    out = {"idx": idx, "question": x["question"], "answer": x["answer"], "order": x["question_order"],
           "deception": x["deception"], "story": [e["text"] for e in events], "timeline": steps,
           "chain": chain, "entity": entity, "secondorder": b.value, "ok": b.value == x["answer"],
           "explain": tools.explain(sid, chain, entity) if chain else None, "evolution": evolution, "reasoning": reasoning,
           "llm": llm, "build_ms": round(ms, 1), "stats": sc.stats(),
           "minds": {a: sc.perspectives(a) for a in sc.agents}}
    sc.delete()
    return out


@app.get("/api/hitom")
def hitom_list(order: int = 4, deception: bool = True, limit: int = 30):
    xs = _hitom()
    llm = _load_results("llm_claude-opus-5-5.json") or {}
    g = {r["idx"]: r for r in (_load_results("graph_parsed.json") or [])}
    out = []
    for i, x in enumerate(xs):
        if x["question_order"] == order and x["deception"] == deception:
            out.append({"idx": i, "question": x["question"], "so_ok": g.get(i, {}).get("ok"),
                        "opus_ok": llm.get(str(i), {}).get("ok")})
    # interesting first: SecondOrder right, LLM wrong
    out.sort(key=lambda r: (not (r["so_ok"] and r["opus_ok"] is False), r["idx"]))
    return out[:limit]


@app.get("/api/eval")
def eval_summary():
    p = os.path.join(RESULTS, "summary.json")
    if os.path.exists(p):
        return json.load(open(p))
    return {"note": "run eval/summarise.py"}


@app.get("/healthz")
def healthz():
    return {"ok": True}
