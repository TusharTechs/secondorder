"""Synthetic demo scenarios (no real people or customer data)."""
from __future__ import annotations

from .engine import Scenario

SUPPORT_SID = "support"

# unrelated channel traffic (synthetic) - the noise a transcript handoff drags along
OPS_CHATTER = [
    ("Finance", "Morning all. Card processor maintenance window tonight 01:00-01:30 UTC, refunds will queue."),
    ("Escalation", "Ticket #4398: customer asking for an invoice copy with VAT number, sending it over now."),
    ("Billing", "#4402 double charge confirmed, reversing the duplicate $54.20."),
    ("Finance", "Reminder: refunds over $200 need a second approver this week (audit)."),
    ("Escalation", "#4405 courier lost the parcel, filed a claim with the carrier, ref CL-88812."),
    ("Billing", "Anyone know if the spring promo code SPRING15 stacks with loyalty points? Customer on #4407 asking."),
    ("Finance", "It doesn't stack - one discount per order per the T&Cs section 4.2."),
    ("Escalation", "#4409 asked to change delivery address after dispatch, told them to use the carrier portal."),
    ("Billing", "Thanks. Closing #4407 with an explanation."),
    ("Escalation", "Heads up: warehouse B is short on lamp SKUs (LMP-220) until the 28th."),
    ("Finance", "#4412 chargeback received, gathering delivery proof."),
    ("Billing", "#4413 wants to split payment across two cards - not supported, offered a gift card route."),
    ("Escalation", "Who's covering the APAC queue tomorrow? I'm out after 3pm."),
    ("Finance", "I can take APAC until 6pm."),
    ("Billing", "Updated the macro for damaged-item photos, please use v3 from now on."),
    ("Escalation", "#4415 replacement delivered, closing."),
    ("Finance", "Month-end close starts Thursday, please get refund approvals in by Wednesday EOD."),
    ("Billing", "OK, logging off in 10."),
    ("Escalation", "#4417 asking about warranty on the desk fan - 12 months, sent the policy link."),
    ("Finance", "Processor maintenance moved to 02:00 UTC."),
    ("Escalation", "#4419 wants express shipping upgrade, quoted $12."),
]
ORG_SID = "org"


def build_support(sid: str = SUPPORT_SID) -> Scenario:
    """A support crew of AI agents and one customer. The refund decision changes in an internal channel
    the customer and the Shipping agent never saw; Billing goes off shift before the replacement is approved."""
    sc = Scenario(sid, depth=3, trust="credulous")
    sc.delete()
    sc = Scenario(sid, depth=3, trust="credulous")
    sc._register("Maya", "Billing", "Shipping", "Escalation", "Finance")
    sc.enter(["Maya", "Billing"], "chat-billing", text="Maya opens a chat with the Billing agent.")
    sc.say("Maya", "chat-billing", "order_4411", "arrived damaged", changes_world=True,
           text="Maya: my order #4411 (a $129 lamp) arrived cracked.")
    sc.say("Billing", "chat-billing", "refund_4411", "approved", changes_world=True,
           text="Billing: Sorry about that! I've approved a full $129 refund for order #4411.")
    sc.exit("Maya", text="Maya leaves the chat.")
    sc.exit("Billing", text="Billing closes the chat.")
    sc.enter(["Billing", "Finance", "Escalation"], "ops-internal", text="Billing, Finance and Escalation are in #ops-internal.")
    for i, (who, msg) in enumerate(OPS_CHATTER[:9]):
        sc.chatter("ops-internal", f"{who}: {msg}", actor=who)
    sc.report("Billing", "ops-internal", "Maya", "refund_4411", "approved",
              text="Billing: FYI, I told the customer on #4411 that her refund is approved.")
    sc.say("Finance", "ops-internal", "refund_4411", "rejected", changes_world=True,
           text="Finance: Rejecting the #4411 refund - the order is 41 days old (policy is 30). Offer a replacement instead.")
    for who, msg in OPS_CHATTER[9:18]:
        sc.chatter("ops-internal", f"{who}: {msg}", actor=who)
    sc.exit("Billing", text="Billing goes off shift.")
    sc.say("Escalation", "ops-internal", "replacement_4411", "approved", changes_world=True,
           text="Escalation: Approved a free replacement lamp for #4411, ships tomorrow.")
    for who, msg in OPS_CHATTER[18:]:
        sc.chatter("ops-internal", f"{who}: {msg}", actor=who)
    sc.exit("Finance", text="Finance leaves #ops-internal.")
    sc.exit("Escalation", text="Escalation leaves #ops-internal.")
    return sc


def handoff(sc: Scenario, sender: str, receiver: str, delta: dict):
    """Write a computed handoff delta into memory as private messages (sender -> receiver)."""
    for f in delta["facts"]:
        if f.get("second_order"):
            sc._apply(f["entity"], {(receiver, f["about"]): (f["value"], "reported", sender)},
                      sc._record("tell", f"{sender} -> {receiver} (handoff): {f['tell']}.", actor=sender,
                                 entity=f["entity"], witnesses=[sender, receiver]))
        else:
            sc.tell(sender, receiver, f["entity"], f["tell"],
                    text=f"{sender} -> {receiver} (handoff): {f['entity']} is {f['tell']}.")
    sc.save()


def build_org(sid: str = ORG_SID) -> Scenario:
    """Company-brain variant: a deploy-freeze decision changed in a thread only part of the org saw."""
    sc = Scenario(sid, depth=2, trust="credulous")
    sc.delete()
    sc = Scenario(sid, depth=2, trust="credulous")
    people = ["Asha", "Ben", "Chen", "Dara", "Eli", "Fatima", "Gus"]
    sc._register(*people)
    sc.enter(people, "all-hands", text="Everyone is at Monday all-hands.")
    sc.say("Asha", "all-hands", "deploy_freeze", "starts Friday", changes_world=True,
           text="Asha (VP Eng): Deploy freeze starts Friday for the Q4 launch.")
    sc.say("Asha", "all-hands", "launch_date", "Nov 3", changes_world=True, text="Asha: Launch is Nov 3.")
    for p in people:
        sc.exit(p)
    sc.enter(["Asha", "Chen", "Dara"], "thread-launch", text="Asha, Chen and Dara in the #launch thread.")
    sc.say("Chen", "thread-launch", "launch_date", "Nov 10", changes_world=True,
           text="Chen: Payments vendor slipped a week - launch moves to Nov 10.")
    sc.say("Asha", "thread-launch", "deploy_freeze", "starts next Friday", changes_world=True,
           text="Asha: Then the freeze moves to *next* Friday.")
    sc.report("Dara", "thread-launch", "Eli", "deploy_freeze", "starts Friday",
              text="Dara: Eli's team is planning to rush their migration in before this Friday.")
    for p in ["Asha", "Chen", "Dara"]:
        sc.exit(p)
    return sc
