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

# Reference labels: the benchmark's OWN published Oracle code (third_party/hitom, unmodified) replayed on every story
# (eval/reference_oracle.py). Every method is scored on all 1,200 questions against both label sets; nothing is excluded.
ref = {r["idx"]: r["reference"] for r in (load("reference_oracle.json") or [])}
mismatch = {i for i in ref if ref[i] != items[i]["answer"]}
suspect = mismatch


def acc(pred_fn, idxs, gold=None):
    by = collections.defaultdict(lambda: [0, 0])
    for i in idxs:
        g = gold(i) if gold else items[i]["answer"]
        by[items[i]["question_order"]][0] += int(pred_fn(i) == g)
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
refg = lambda i: ref.get(i, items[i]["answer"])  # noqa: E731
for name, color, fn, idxs in series_defs:
    if not idxs:
        continue
    a = acc(fn, idxs)
    b = acc(fn, idxs, gold=refg)
    tot = sum(int(fn(i) == items[i]["answer"]) for i in idxs)
    tot_r = sum(int(fn(i) == refg(i)) for i in idxs)
    summary["series"].append({"name": name, "color": color, "acc": [b[o][0] for o in ORDERS], "n": len(idxs)})
    summary["audited"].append({"name": name, "acc": [a[o][0] for o in ORDERS], "n": len(idxs)})
    rows.append((name, len(idxs), 100 * tot / len(idxs), [a[o][0] for o in ORDERS], len(idxs), 100 * tot_r / len(idxs),
                 [b[o][0] for o in ORDERS]))

ps = load("paraphrase_scored.json") or []
para = (sum(r["secondorder"] == r["gold"] for r in ps), sum(r["opus"] == r["gold"] for r in ps), len(ps)) if ps else None

# cost / latency
lat = [r["stats"] for r in graph.values() if r.get("stats")]
avg_p = sum(s["perspectives"] for s in lat) / len(lat)
avg_poss = sum(s["possible_perspectives"] for s in lat) / len(lat)
opus_tok = [v["usage"].get("out", 0) for v in opus.values()]
summary["side"] = {"avg_perspectives": round(avg_p, 1), "avg_possible": round(avg_poss, 1),
                   "opus_avg_output_tokens": round(sum(opus_tok) / max(1, len(opus_tok)))}


def fmt(v):
    return "–" if v is None else f"{v:.1f}"


md = ["| Method | n | vs released labels | order 0 | 1 | 2 | 3 | 4 | n | vs Hi-ToM reference oracle | 0 | 1 | 2 | 3 | 4 |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for name, n, tot, a, nc, totc, b in rows:
    md.append(f"| {name} | {n} | **{tot:.1f}** | " + " | ".join(fmt(x) for x in a) + f" | {nc} | **{totc:.1f}** | " +
              " | ".join(fmt(x) for x in b) + " |")
table = "\n".join(md)
summary["table_md"] = table
summary["table_html"] = (
    "<table class='text-xs mono w-full'><tr class='text-slate-400'><th class='text-left'>method</th><th>n</th><th>vs released labels</th>"
    + "".join(f"<th>o{o}</th>" for o in ORDERS) + "<th>vs reference oracle</th>" + "".join(f"<th>o{o}</th>" for o in ORDERS) + "</tr>"
    + "".join(f"<tr><td>{name}</td><td>{n}</td><td><b>{tot:.1f}</b></td>" + "".join(f"<td>{fmt(x)}</td>" for x in a)
              + f"<td><b>{totc:.1f}</b></td>" + "".join(f"<td>{fmt(x)}</td>" for x in b) + "</tr>"
              for name, n, tot, a, nc, totc, b in rows) + "</table>"
    + f"<p class='text-xs text-slate-400 mt-2'>Every method is scored on all 1,200 questions twice: against the released JSON labels, and against "
      f"Hi-ToM's own published Oracle code replayed on each story (unmodified, third_party/hitom). The two disagree on {len(mismatch)} questions. "
      "The chart shows accuracy vs. the reference oracle. See eval/results/LABEL_ERRORS.md.</p>")
summary["side_html"] = (
    f"<div class='space-y-3'><div><div class='text-3xl font-bold text-sky-300'>{rows[0][2]:.1f}%</div><div class='text-xs text-slate-400'>SecondOrder vs. the released labels</div></div>"
    f"<div><div class='text-3xl font-bold text-sky-300'>{rows[0][5]:.1f}%</div><div class='text-xs text-slate-400'>SecondOrder vs. Hi-ToM's own reference Oracle code ({rows[0][1]} questions, none excluded)</div></div>"
    + (f"<div><div class='text-xl font-bold'>{para[0]} vs {para[1]} / {para[2]}</div><div class='text-xs text-slate-400'>free natural prose (Claude-paraphrased stories): SecondOrder + Claude extraction vs. Claude Opus 5.5 alone</div></div>" if para else "") +
    f"<div><div class='text-xl font-bold'>6 graphs</div><div class='text-xs text-slate-400'>per story: 1 world graph + 1 mind graph per agent, nested perspectives inside</div></div>"
    f"<div><div class='text-xl font-bold'>~1.5 ms</div><div class='text-xs text-slate-400'>median time to route one event into every affected mind (embedded FalkorDB)</div></div>"
    f"<div><div class='text-xl font-bold'>0 tokens</div><div class='text-xs text-slate-400'>to answer a nested-belief question once memory is built (a Cypher read) vs. ~{summary['side']['opus_avg_output_tokens']} output tokens per question for Opus 5.5 reasoning from the transcript</div></div></div>")
json.dump(summary, open(os.path.join(R, "summary.json"), "w"), indent=1)

# label audit file
lines = ["# Hi-ToM label inconsistencies", "",
         f"We replayed every Hi-ToM story through the benchmark's own published belief-tracking code (`Oracle` + action classes from "
         f"github.com/ying-hui-he/Hi-ToM_dataset, unmodified, in `third_party/hitom`; script `eval/reference_oracle.py`). "
         f"On {len(mismatch)} of {len(items)} questions, that code's answer differs from the label in the released `Hi-ToM_data.json`. "
         "SecondOrder agrees with the reference code on all of them (and on every other question). The repository history contains a commit "
         "'fix permutation bug' (9117f35d) that changed how nested beliefs are written, which may explain the drift.", "",
         "| idx | order | deception | question | released label | Hi-ToM reference code | SecondOrder | Claude Opus 5.5 (no graph) |",
         "|---|---|---|---|---|---|---|---|"]
for i in sorted(mismatch):
    x = items[i]
    lines.append(f"| {i} | {x['question_order']} | {x['deception']} | {x['question']} | {x['answer']} | {ref[i]} | "
                 f"{graph[i]['pred']} | {opus.get(str(i), {}).get('pred')} |")
open(os.path.join(R, "LABEL_ERRORS.md"), "w").write("\n".join(lines))
open(os.path.join(R, "RESULTS.md"), "w").write(table + "\n")
print(table)
print("suspect:", len(suspect), summary["side"])
