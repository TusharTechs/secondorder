"""LLM-only baseline and LLM event extraction on Hi-ToM.

usage:
  python -m eval.run_llm answer  --model claude-opus-5-5 [--limit N] [--per-cell K]
  python -m eval.run_llm extract --model claude-opus-5-5 [--per-cell K]
Results are cached per item so reruns only call the API for missing items.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from secondorder import llm  # noqa: E402
from secondorder.hitom import NAME  # noqa: E402,F401

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "hitom.json")
OUT = os.path.join(os.path.dirname(__file__), "results")


def items(per_cell=None, limit=None, seed=7):
    xs = json.load(open(DATA))["data"]
    for i, x in enumerate(xs):
        x["idx"] = i
    if per_cell:
        rnd = random.Random(seed)
        cells = collections.defaultdict(list)
        for x in xs:
            cells[(x["question_order"], x["deception"])].append(x)
        xs = [y for k in sorted(cells) for y in rnd.sample(cells[k], min(per_cell, len(cells[k])))]
    return xs[:limit] if limit else xs


def story_only(x):
    return "\n".join(l for l in x["story"].split("\n") if l.strip() and l.strip()[0].isdigit())


async def run_answer(model, xs, path):
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [x for x in xs if str(x["idx"]) not in cache]
    print(f"{model}: {len(todo)} to run ({len(cache)} cached)")

    async def one(x):
        text, usage = await llm.ask(model, x["prompt"] + llm.ANSWER_SUFFIX, effort="medium")
        pred = llm.parse_answer(text, x["choices"])
        return x["idx"], dict(pred=pred, answer=x["answer"], ok=pred == x["answer"], order=x["question_order"],
                              deception=x["deception"], usage=usage, text=text[-600:])

    done = 0
    for chunk in range(0, len(todo), 48):
        res = await llm.gather_limited([one(x) for x in todo[chunk:chunk + 48]], limit=24)
        for r in res:
            if isinstance(r, Exception):
                print("err", repr(r)[:200])
                continue
            cache[str(r[0])] = r[1]
        done += len(res)
        json.dump(cache, open(path, "w"))
        print(f"  {done}/{len(todo)}", flush=True)
    return cache


async def run_extract(model, xs, path):
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [x for x in xs if str(x["idx"]) not in cache]
    print(f"extract {model}: {len(todo)} to run ({len(cache)} cached)")

    async def one(x):
        evts, usage = await llm.extract_events(story_only(x), model=model)
        return x["idx"], evts, usage

    done = 0
    for chunk in range(0, len(todo), 48):
        res = await llm.gather_limited([one(x) for x in todo[chunk:chunk + 48]], limit=24)
        for r in res:
            if isinstance(r, Exception):
                print("err", repr(r)[:200])
                continue
            cache[str(r[0])] = r[1]
        done += len(res)
        json.dump(cache, open(path, "w"))
        print(f"  {done}/{len(todo)}", flush=True)
    return cache


def summarise(cache, name):
    agg = collections.defaultdict(lambda: [0, 0])
    tin = tout = 0
    for r in cache.values():
        agg[r["order"]][0] += r["ok"]
        agg[r["order"]][1] += 1
        tin += r["usage"].get("in", 0)
        tout += r["usage"].get("out", 0)
    print(name, {k: f"{v[0]}/{v[1]}" for k, v in sorted(agg.items())}, "tokens in/out", tin, tout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["answer", "extract"])
    ap.add_argument("--model", default=llm.OPUS)
    ap.add_argument("--per-cell", type=int)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    xs = items(a.per_cell, a.limit)
    if a.mode == "answer":
        path = os.path.join(OUT, f"llm_{a.model}.json")
        cache = asyncio.run(run_answer(a.model, xs, path))
        summarise(cache, a.model)
    else:
        path = os.path.join(OUT, f"events_{a.model}.json")
        asyncio.run(run_extract(a.model, xs, path))


if __name__ == "__main__":
    main()
