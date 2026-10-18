"""Scale benchmark on FalkorDB.

1. Multi-tenancy: thousands of isolated scenarios (1 world + 5 mind graphs each) in ONE FalkorDB instance;
   event-routing latency as the number of graphs grows.
2. Agents x depth: cost of one broadcast event and of a nested read as agents/depth grow.
3. Index ablation: Perspective(chain) range index on vs off.
usage: python -m eval.scale [--tenants 1700]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from secondorder.db import conn  # noqa: E402
from secondorder.engine import Scenario  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "results", "scale.json")


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


def tenant(i, lat):
    sc = Scenario(f"t{i}", depth=3, trust="credulous")
    names = ["A", "B", "C", "D", "E"]
    sc._register(*names)
    t0 = time.perf_counter(); sc.enter(names, "room"); lat.append(time.perf_counter() - t0)
    t0 = time.perf_counter(); sc.say("A", "room", "plan", "v1", changes_world=True); lat.append(time.perf_counter() - t0)
    sc.exit("E"); sc.exit("D")
    t0 = time.perf_counter(); sc.say("B", "room", "plan", "v2", changes_world=True); lat.append(time.perf_counter() - t0)
    t0 = time.perf_counter(); sc.tell("A", "E", "plan", "v2"); lat.append(time.perf_counter() - t0)
    return sc


def multitenant(n):
    rows, lat, reads = [], [], []
    t_start = time.perf_counter()
    for i in range(n):
        tenant(i, lat)
        if (i + 1) % max(1, n // 10) == 0:
            sc = Scenario.load(f"t{i}")
            r = []
            for _ in range(50):
                t0 = time.perf_counter(); sc.resolve(["A", "B", "E"], "plan"); r.append(time.perf_counter() - t0)
            graphs = len(conn().execute_command("GRAPH.LIST"))
            mem = conn().info("memory")["used_memory"]
            rows.append({"tenants": i + 1, "graphs": graphs, "event_p50_ms": round(pct(lat[-400:], 50) * 1000, 2),
                         "event_p99_ms": round(pct(lat[-400:], 99) * 1000, 2), "read_p50_ms": round(pct(r, 50) * 1000, 3),
                         "used_memory_mb": round(mem / 1e6, 1)})
            print(rows[-1], flush=True)
    return {"rows": rows, "total_s": round(time.perf_counter() - t_start, 1)}


def agents_depth():
    out = []
    for depth in (2, 3):
        for n in (4, 8, 12, 16) if depth == 3 else (4, 8, 16, 32):
            for index in (True, False):
                sid = f"ad{n}_{depth}_{int(index)}"
                sc = Scenario(sid, depth=depth, trust="credulous", index=index); sc.delete()
                sc = Scenario(sid, depth=depth, trust="credulous", index=index)
                names = [f"a{i}" for i in range(n)]
                sc._register(*names)
                sc.enter(names, "room")
                ev = []
                for k in range(3):
                    t0 = time.perf_counter(); sc.say(names[0], "room", "x", f"v{k}", changes_world=True); ev.append(time.perf_counter() - t0)
                for a in names[: n // 2]:
                    sc.exit(a)
                t0 = time.perf_counter(); sc.say(names[-1], "room", "x", "late", changes_world=True); ev.append(time.perf_counter() - t0)
                rd = []
                for _ in range(30):
                    t0 = time.perf_counter(); sc.resolve(names[: depth], "x"); rd.append(time.perf_counter() - t0)
                st = sc.stats()
                out.append({"agents": n, "depth": depth, "index": index, "perspectives": st["perspectives"],
                            "possible": st["possible_perspectives"], "belief_edges": st["belief_edges"],
                            "event_ms_median": round(statistics.median(ev) * 1000, 1),
                            "read_ms_median": round(statistics.median(rd) * 1000, 2)})
                print(out[-1], flush=True)
                sc.delete()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenants", type=int, default=1700)
    a = ap.parse_args()
    res = {"agents_depth": agents_depth(), "multitenant": multitenant(a.tenants)}
    json.dump(res, open(OUT, "w"), indent=1)
    print("saved", OUT)
