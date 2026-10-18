"""Agent-task evaluation: does the agent correct a customer's stale belief it never saw being formed?

20 synthetic support scenarios (varied customers, products, decisions). In each, agent A tells the customer X in chat,
X is changed to Y in an internal channel the customer never sees, and a handoff goes to agent B, who receives the
customer's next message (which never restates X). Three arms for agent B, all Claude Opus 5.5:
  flat        - B's own facts only (a normal agent memory after the handoff)
  transcript  - flat + the full transcript the sender saw (the common "dump the history" handoff)
  secondorder - flat + theory-of-mind tools over B's own (ACL-scoped) mind graph
A Claude Opus 5.5 judge checks whether the reply explicitly corrects the customer's outdated understanding.

usage: python -m eval.run_agents [--n 20]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import anthropic  # noqa: E402

from secondorder import agent, tools  # noqa: E402
from secondorder.engine import Scenario  # noqa: E402
from secondorder.llm import OPUS  # noqa: E402
from secondorder.scenarios import OPS_CHATTER, handoff  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "results", "agent_eval.json")
ARMS = ("flat", "transcript", "secondorder", "context")
CHATTER_X = 1

CASES = [
    # (entity, told value, new value, extra entity, extra value, what the customer bought)
    ("refund", "approved", "rejected", "replacement", "approved"),
    ("delivery_date", "Friday", "next Wednesday", "shipping_upgrade", "free express"),
    ("discount_code", "valid", "revoked", "store_credit", "$15 issued"),
    ("warranty_repair", "covered", "not covered", "repair_quote", "$40"),
    ("cancellation", "confirmed", "too late to cancel", "return_label", "emailed"),
]
CUSTOMERS = ["Maya", "Arjun", "Lena", "Tomás", "Aiko", "Noor", "Femi", "Priya", "Jonas", "Sara"]
MESSAGES = ["Hi! Any update on my order?", "Hello, just following up on my ticket.", "Hey, what's the status?",
            "Hi there, anything new on my case?"]


def build(i: int, rnd: random.Random) -> dict:
    ent, told, new, extra, extra_v = CASES[i % len(CASES)]
    cust = CUSTOMERS[i % len(CUSTOMERS)]
    oid = 5000 + i
    e, x = f"{ent}_{oid}", f"{extra}_{oid}"
    sid = f"ae{i}"
    sc = Scenario(sid, depth=3, trust="credulous")
    sc.delete()
    sc = Scenario(sid, depth=3, trust="credulous")
    sc._register(cust, "Billing", "Shipping", "Escalation", "Finance")
    sc.enter([cust, "Billing"], "chat-billing")
    sc.say("Billing", "chat-billing", e, told, changes_world=True,
           text=f"Billing: Good news {cust}, for order #{oid} the {ent.replace('_', ' ')} is {told}.")
    sc.exit(cust)
    sc.exit("Billing")
    sc.enter(["Billing", "Finance", "Escalation"], "ops-internal")
    pool = [(w, f"[{k}] {m}") for k in range(CHATTER_X) for w, m in OPS_CHATTER]
    chatter = rnd.sample(pool, 12 * CHATTER_X)
    for who, msg in chatter[:len(chatter) // 2]:
        sc.chatter("ops-internal", f"{who}: {msg}", actor=who)
    sc.report("Billing", "ops-internal", cust, e, told,
              text=f"Billing: FYI I told {cust} on #{oid} that the {ent.replace('_', ' ')} is {told}.")
    sc.say("Finance", "ops-internal", e, new, changes_world=True,
           text=f"Finance: Correction on #{oid}: the {ent.replace('_', ' ')} is {new}.")
    sc.exit("Billing")
    sc.say("Escalation", "ops-internal", x, extra_v, changes_world=True,
           text=f"Escalation: For #{oid} I've arranged {extra.replace('_', ' ')}: {extra_v}.")
    for who, msg in chatter[len(chatter) // 2:]:
        sc.chatter("ops-internal", f"{who}: {msg}", actor=who)
    sc.exit("Finance")
    sc.exit("Escalation")
    transcript = "\n".join(ev["text"] for ev in sc.timeline() if "Escalation" in ev["witnesses"] and ev["kind"] != "noise")
    handoff(sc, "Escalation", "Shipping", tools.handoff_delta(sid, "Escalation", "Shipping", about=str(oid)))
    return {"sid": sid, "customer": cust, "entity": e, "told": told, "new": new, "message": MESSAGES[i % len(MESSAGES)],
            "transcript": transcript}


JUDGE = """A customer was earlier told: "{entity} = {told}". That is now outdated; the truth is "{entity} = {new}".
The customer's new message did not mention it. Here is the support agent's reply:
---
{reply}
---
Answer with JSON only: {{"corrects": true/false, "contradicts_truth": true/false}}.
"corrects" = the reply explicitly tells the customer the earlier information changed / is no longer true (not just stating the new value as if new).
"contradicts_truth" = the reply asserts "{told}" as currently true."""


def judge(client, case, reply):
    r = client.messages.create(model=OPUS, max_tokens=2000, output_config={"effort": "low"}, messages=[{
        "role": "user", "content": JUDGE.format(entity=case["entity"], told=case["told"], new=case["new"], reply=reply)}])
    text = "".join(b.text for b in r.content if b.type == "text")
    s = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(s)


def run_arm(case, arm):
    mode = "secondorder" if arm == "secondorder" else "flat"
    extra = ""
    if arm == "transcript":
        extra = f"\n\nHandoff transcript from Escalation (everything they saw):\n{case['transcript']}"
    elif arm == "context":
        extra = "\n\n" + agent.context_block(case["sid"], "Shipping", case["customer"])
    r = agent.run(case["sid"], "Shipping", case["customer"], case["message"], mode=mode, system_extra=extra)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--chatter", type=int, default=1, help="channel-history multiplier (12 lines x N)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    global CHATTER_X, OUT
    CHATTER_X = a.chatter
    if a.out:
        OUT = os.path.join(os.path.dirname(__file__), "results", a.out)
    rnd = random.Random(3)
    cases = [build(i, rnd) for i in range(a.n)]
    client = anthropic.Anthropic(max_retries=4)
    jobs = [(c, arm) for c in cases for arm in ARMS]

    def one(job):
        c, arm = job
        r = run_arm(c, arm)
        reply = (r.get("draft") or {}).get("message", "")
        j = judge(client, c, reply) if reply else {"corrects": False, "contradicts_truth": False}
        return {"sid": c["sid"], "arm": arm, "reply": reply, "tools": [t["tool"] for t in r["trace"]],
                "input_tokens": r.get("input_tokens"), **j}

    with cf.ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(one, jobs))
    json.dump({"cases": [{k: v for k, v in c.items() if k != "transcript"} for c in cases], "rows": rows},
              open(OUT, "w"), indent=1)
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        tok = [r["input_tokens"] for r in rs if r["input_tokens"]]
        print(f"{arm:12s} corrects {sum(r['corrects'] for r in rs)}/{len(rs)}  contradicts {sum(r['contradicts_truth'] for r in rs)}/{len(rs)}"
              f"  avg input tokens {sum(tok) / max(1, len(tok)):.0f}")
    for c in cases:
        Scenario.load(c["sid"]).delete()


if __name__ == "__main__":
    main()
