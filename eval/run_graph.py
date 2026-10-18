"""Run SecondOrder on every Hi-ToM question and score it.

usage: python -m eval.run_graph [--limit N] [--events parsed|llm] [--keep]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from secondorder.engine import Scenario  # noqa: E402
from secondorder.hitom import parse_question, parse_story, run_events  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "hitom.json")
OUT = os.path.join(os.path.dirname(__file__), "results")


def load(limit=None):
    items = json.load(open(DATA))["data"]
    for i, x in enumerate(items):
        x["idx"] = i
    return items[:limit] if limit else items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--events", default="parsed", help="parsed | path to JSON {idx: events} from LLM extraction")
    ap.add_argument("--name", default=None)
    ap.add_argument("--only", default=None, help="comma-separated idx list")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--legacy", action="store_true", help="replicate the pre-fix generator ordering (benchmark audit)")
    a = ap.parse_args()
    items = load(a.limit)
    llm_events = None
    if a.events != "parsed":
        llm_events = json.load(open(a.events))
        items = [x for x in items if str(x["idx"]) in llm_events]
    if a.only:
        keep = {int(i) for i in a.only.split(",")}
        items = [x for x in items if x["idx"] in keep]
    os.makedirs(OUT, exist_ok=True)
    rows, lat = [], []
    t0 = time.time()
    for x in items:
        sid = f"eval{x['idx']}"
        sc = Scenario(sid, depth=4, trust="hitom")
        sc.delete()
        events = llm_events[str(x["idx"])] if llm_events else parse_story(x["story"])
        ts = time.perf_counter()
        try:
            run_events(sc, events, legacy_labels=a.legacy)
            chain, entity = parse_question(x["question"])
            b = sc.resolve(chain, entity)
            pred, err = b.value, None
            # ablations computed on the same graph: a flat memory (stores only the latest fact = world truth)
            # and a per-agent memory without nesting (answers with the first person's own belief)
            flat_pred = sc.truth(entity)
            own_pred = sc.resolve(chain[:1], entity).value if chain else flat_pred
        except Exception as e:  # keep going, record failure
            pred, err, chain = None, repr(e)[:300], []
            flat_pred = own_pred = None
        lat.append((time.perf_counter() - ts) / max(1, len(events)))
        ok = pred == x["answer"]
        rows.append(dict(idx=x["idx"], order=x["question_order"], deception=x["deception"], length=x["story_length"],
                         prompting=x["prompting_type"], question=x["question"], answer=x["answer"], pred=pred, ok=ok,
                         err=err, n_events=len(events), flat_pred=flat_pred, own_pred=own_pred, stats=sc.stats() if not err else None))
        if not a.keep:
            sc.delete()
    name = a.name or ("graph_parsed" if a.events == "parsed" else "graph_llm")
    json.dump(rows, open(os.path.join(OUT, f"{name}.json"), "w"), indent=1)
    agg = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        agg[(r["order"], r["deception"])][0] += r["ok"]
        agg[(r["order"], r["deception"])][1] += 1
    print(f"{name}: {sum(r['ok'] for r in rows)}/{len(rows)} in {time.time()-t0:.1f}s; "
          f"per-event p50 {sorted(lat)[len(lat)//2]*1000:.2f} ms")
    for k in sorted(agg):
        print(f"  order {k[0]} deception {k[1]!s:5}: {agg[k][0]}/{agg[k][1]}")
    errs = [r for r in rows if r["err"]]
    if errs:
        print("errors:", len(errs), errs[0]["err"])


if __name__ == "__main__":
    main()
