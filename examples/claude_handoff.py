"""Prepend SecondOrder context to any LLM call (here: Claude). Requires ANTHROPIC_API_KEY."""
import anthropic
from secondorder import Memory

mem = Memory("handoff-demo", fresh=True)
mem.join(["Maya", "Billing"], "chat")
mem.say("Billing", "refund", "approved", room="chat")
mem.leave("Maya")
mem.join(["Shipping"], "chat")
mem.report("Billing", "Maya", "refund", "approved", room="chat")
mem.set("refund", "rejected", room="chat", by="Finance")

context = mem.context_for("Shipping", talking_to="Maya")
msg = anthropic.Anthropic().messages.create(
    model="claude-opus-5-5", max_tokens=1000,
    system="You are Shipping, a support agent. Use the SecondOrder context.\n" + context,
    messages=[{"role": "user", "content": "Maya: hi, any news on my order?"}])
print(context, "\n---\n", msg.content[-1].text)
