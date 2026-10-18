"""Free-text generality test: Claude rewrites Hi-ToM stories as varied natural prose (no templates).
Then (a) Claude extracts events -> SecondOrder answers, and (b) Claude Opus 5.5 answers from the prose alone.

usage: python -m eval.run_paraphrase [--per-cell 10]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_llm import items, story_only  # noqa: E402
from secondorder import llm  # noqa: E402
from secondorder.engine import Scenario  # noqa: E402
from secondorder.hitom import parse_question, run_events  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "results")
PARA = """Rewrite this story as natural, varied prose, the way a person would narrate it in a chat or a diary.
Vary the wording a lot (e.g. "stepped out", "headed off", "slipped the X into the Y", "whispered to", "announced to everyone"),
merge or split sentences freely, but keep every event, keep their order, and keep the object and container tokens exactly
as written (e.g. green_drawer). Keep the people's names. Do not add events or explanations. Output only the rewritten story.

Story:
{story}"""


async def main(per_cell):
    xs = items(per_cell=per_cell, seed=11)
    path = os.path.join(OUT, "paraphrase.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}

    async def one(x):
        k = str(x["idx"])
        rec = cache.get(k, {})
        if "prose" not in rec:
            rec["prose"], _ = await llm.ask(llm.OPUS, PARA.format(story=story_only(x)), effort="low")
        if "events" not in rec:
            rec["events"], _ = await llm.extract_events(rec["prose"])
        if "opus" not in rec:
            note = x["prompt"][x["prompt"].find("Note:"):] if "Note:" in x["prompt"] else ""
            q = (f"Read the following story and answer the multiple-choice question.\nStory:\n{rec['prose']}\n\n"
                 f"Question: {x['question']}\nChoices: {x['choices']}\n{note}" + llm.ANSWER_SUFFIX)
            text, _ = await llm.ask(llm.OPUS, q, effort="medium")
            rec["opus"] = llm.parse_answer(text, x["choices"])
        return k, rec

    res = await llm.gather_limited([one(x) for x in xs], limit=20)
    for r in res:
        if isinstance(r, Exception):
            print("err", repr(r)[:200])
            continue
        cache[r[0]] = r[1]
    json.dump(cache, open(path, "w"), indent=1)

    agg = collections.defaultdict(lambda: [0, 0, 0])
    rows = []
    for x in xs:
        rec = cache.get(str(x["idx"]))
        if not rec:
            continue
        sc = Scenario(f"para{x['idx']}", depth=4, trust="hitom")
        sc.delete()
        sc = Scenario(f"para{x['idx']}", depth=4, trust="hitom")
        try:
            run_events(sc, rec["events"])
            chain, ent = parse_question(x["question"])
            pred = sc.resolve(chain, ent).value
        except Exception as e:
            pred = None
            print("graph err", x["idx"], repr(e)[:150])
        sc.delete()
        o = x["question_order"]
        agg[o][0] += pred == x["answer"]
        agg[o][1] += rec["opus"] == x["answer"]
        agg[o][2] += 1
        rows.append({"idx": x["idx"], "order": o, "gold": x["answer"], "secondorder": pred, "opus": rec["opus"]})
    json.dump(rows, open(os.path.join(OUT, "paraphrase_scored.json"), "w"), indent=1)
    for o in sorted(agg):
        a = agg[o]
        print(f"order {o}: SecondOrder+extraction {a[0]}/{a[2]}  Opus alone {a[1]}/{a[2]}")
    print("total", sum(a[0] for a in agg.values()), sum(a[1] for a in agg.values()), sum(a[2] for a in agg.values()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=10)
    asyncio.run(main(ap.parse_args().per_cell))
