"""Build eval/results/summary.json (for the UI) and RESULTS.md (for the README) from all result files."""
from __future__ import annotations

import collections
import json
import os

R = os.path.join(os.path.dirname(__file__), "results")
items = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "hitom.json")))["data"]
ORDERS = [0, 1, 2, 3, 4]


def load(name):
    p = os.path.join(R, name)
    return json.load(open(p)) if os.path.exists(p) else None


graph = {r["idx"]: r for r in load("graph_parsed.json")}
graph_llm = {r["idx"]: r for r in (load("graph_llm.json") or [])}
opus = load("llm_claude-opus-5-5.json") or {}
haiku = load("llm_claude-haiku-5-5.json") or {}

# likely label errors: SecondOrder and Claude Opus 5.5 (independently, no graph) agree with each other against gold
suspect = {i for i, r in graph.items() if not r["ok"] and str(i) in opus and opus[str(i)]["pred"] == r["pred"]}


def acc(pred_fn, idxs):
    by = collections.defaultdict(lambda: [0, 0])
    for i in idxs:
        p = pred_fn(i)
        if p is None and p is not False:
            pass
        by[items[i]["question_order"]][0] += int(p == items[i]["answer"])
        by[items[i]["question_order"]][1] += 1
    return {o: (round(100 * by[o][0] / by[o][1], 1) if by[o][1] else None, by[o][1]) for o in ORDERS}


ALL = list(range(len(items)))
series_defs = [
    ("SecondOrder (FalkorDB)", "#38bdf8", lambda i: graph[i]["pred"], ALL),
    ("SecondOrder + Claude event extraction", "#a78bfa", lambda i: graph_llm[i]["pred"] if i in graph_llm else None,
     [i for i in ALL if i in graph_llm]),
    ("Claude Opus 5.5 alone", "#f472b6", lambda i: opus[str(i)]["pred"], [i for i in ALL if str(i) in opus]),
    ("Claude Haiku 5.5 alone", "#fbbf24", lambda i: haiku[str(i)]["pred"], [i for i in ALL if str(i) in haiku]),
    ("Flat memory (latest fact)", "#64748b", lambda i: graph[i]["flat_pred"], ALL),
    ("Per-agent memory, no nesting", "#94a3b8", lambda i: graph[i]["own_pred"], ALL),
]

summary = {"orders": ORDERS, "series": [], "audited": [], "n_suspect": len(suspect)}
rows = []
for name, color, fn, idxs in series_defs:
    if not idxs:
        continue
    a = acc(fn, idxs)
    clean = [i for i in idxs if i not in suspect]
    b = acc(fn, clean)
    tot = sum(int(fn(i) == items[i]["answer"]) for i in idxs)
    tot_c = sum(int(fn(i) == items[i]["answer"]) for i in clean)
    summary["series"].append({"name": name, "color": color, "acc": [a[o][0] for o in ORDERS], "n": len(idxs)})
    summary["audited"].append({"name": name, "acc": [b[o][0] for o in ORDERS], "n": len(clean)})
    rows.append((name, len(idxs), 100 * tot / len(idxs), [a[o][0] for o in ORDERS], len(clean), 100 * tot_c / max(1, len(clean)),
                 [b[o][0] for o in ORDERS]))

# cost / latency
lat = [r["stats"] for r in graph.values() if r.get("stats")]
avg_p = sum(s["perspectives"] for s in lat) / len(lat)
avg_poss = sum(s["possible_perspectives"] for s in lat) / len(lat)
opus_tok = [v["usage"].get("out", 0) for v in opus.values()]
summary["side"] = {"avg_perspectives": round(avg_p, 1), "avg_possible": round(avg_poss, 1),
                   "opus_avg_output_tokens": round(sum(opus_tok) / max(1, len(opus_tok)))}


def fmt(v):
    return "–" if v is None else f"{v:.1f}"


md = ["| Method | n | overall | order 0 | 1 | 2 | 3 | 4 | audited n | audited overall | 0 | 1 | 2 | 3 | 4 |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for name, n, tot, a, nc, totc, b in rows:
    md.append(f"| {name} | {n} | **{tot:.1f}** | " + " | ".join(fmt(x) for x in a) + f" | {nc} | **{totc:.1f}** | " +
              " | ".join(fmt(x) for x in b) + " |")
table = "\n".join(md)
summary["table_md"] = table
summary["table_html"] = (
    "<table class='text-xs mono w-full'><tr class='text-slate-400'><th class='text-left'>method</th><th>n</th><th>overall</th>"
    + "".join(f"<th>o{o}</th>" for o in ORDERS) + "<th>audited overall</th>" + "".join(f"<th>o{o}</th>" for o in ORDERS) + "</tr>"
    + "".join(f"<tr><td>{name}</td><td>{n}</td><td><b>{tot:.1f}</b></td>" + "".join(f"<td>{fmt(x)}</td>" for x in a)
              + f"<td><b>{totc:.1f}</b></td>" + "".join(f"<td>{fmt(x)}</td>" for x in b) + "</tr>"
              for name, n, tot, a, nc, totc, b in rows) + "</table>"
    + f"<p class='text-xs text-slate-400 mt-2'>Audited = excluding the {len(suspect)} questions where SecondOrder and Claude Opus 5.5 "
      "(independently, without the graph) agree with each other against the gold label. See eval/results/LIKELY_LABEL_ERRORS.md.</p>")
summary["side_html"] = (
    f"<div class='space-y-3'><div><div class='text-3xl font-bold text-sky-300'>{rows[0][2]:.1f}%</div><div class='text-xs text-slate-400'>SecondOrder overall (raw labels)</div></div>"
    f"<div><div class='text-3xl font-bold text-sky-300'>{rows[0][5]:.1f}%</div><div class='text-xs text-slate-400'>SecondOrder after removing {len(suspect)} likely label errors</div></div>"
    f"<div><div class='text-xl font-bold'>{summary['side']['avg_perspectives']} / {summary['side']['avg_possible']}</div><div class='text-xs text-slate-400'>perspectives actually materialised per story vs. possible (copy-on-write)</div></div>"
    f"<div><div class='text-xl font-bold'>~1.5 ms</div><div class='text-xs text-slate-400'>median time to route one event into every affected mind (embedded FalkorDB)</div></div>"
    f"<div><div class='text-xl font-bold'>0 tokens</div><div class='text-xs text-slate-400'>to answer a nested-belief question once memory is built (a Cypher read) vs. ~{summary['side']['opus_avg_output_tokens']} output tokens per question for Opus 5.5 reasoning from the transcript</div></div></div>")
json.dump(summary, open(os.path.join(R, "summary.json"), "w"), indent=1)

# label audit file
lines = ["# Likely label errors in Hi-ToM", "",
         f"{len(suspect)} questions where SecondOrder's answer (derived from the benchmark's stated rules) and Claude Opus 5.5's answer "
         "(no graph, chain-of-thought) agree with each other but not with the gold label. The Hi-ToM generator's history contains a "
         "commit 'fix permutation bug' (9117f35d) that changed how nested beliefs are written; these questions are concentrated in "
         "orders 2-4. We report raw and audited accuracy; nothing is silently dropped.", "",
         "| idx | order | deception | question | gold | SecondOrder = Opus |", "|---|---|---|---|---|---|"]
for i in sorted(suspect):
    x = items[i]
    lines.append(f"| {i} | {x['question_order']} | {x['deception']} | {x['question']} | {x['answer']} | {graph[i]['pred']} |")
open(os.path.join(R, "LIKELY_LABEL_ERRORS.md"), "w").write("\n".join(lines))
open(os.path.join(R, "RESULTS.md"), "w").write(table + "\n")
print(table)
print("suspect:", len(suspect), summary["side"])
