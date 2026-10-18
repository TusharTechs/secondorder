"""The classic Sally-Anne false-belief test, as graph memory."""
from secondorder import Memory

m = Memory("sally-anne", depth=3, fresh=True)
m.join(["Sally", "Anne"], "room")
m.set("marble", "basket", room="room")
m.leave("Sally")
m.set("marble", "box", room="room", by="Anne")
print("Where is the marble?                       ", m.truth("marble"))
print("Where will Sally look?                     ", m.believes("Sally", "marble"))
print("Where does Anne think Sally will look?     ", m.believes(["Anne", "Sally"], "marble"))
print("Why?", m.explain(["Anne", "Sally"], "marble")["steps"])
