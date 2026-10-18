"""5-line quickstart: run with `python examples/quickstart.py` (embedded FalkorDB, no setup)."""
from secondorder import Memory

mem = Memory("quickstart", fresh=True)
mem.join(["Maya", "Billing"], "chat")
mem.say("Billing", "refund", "approved", room="chat")
mem.leave("Maya")
mem.set("refund", "rejected", room="chat", by="Finance")       # Maya has left: she never sees this

print(mem.believes("Maya", "refund"))                # approved   <- false belief
print(mem.believes(["Billing", "Maya"], "refund"))   # approved   <- Billing knows Maya still thinks so
print(mem.context_for("Billing", talking_to="Maya"))
for f in mem.false_beliefs():
    print("!", f["summary"])
