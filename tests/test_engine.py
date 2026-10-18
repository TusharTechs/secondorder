"""Core behaviour tests (run: FALKORDB_LITE_PATH=/tmp/so_test.db python -m pytest -q)."""
import os

os.environ.setdefault("FALKORDB_LITE_PATH", "/tmp/so_test.db")

from secondorder import tools  # noqa: E402
from secondorder.agent_view import AgentView  # noqa: E402
from secondorder.engine import Scenario  # noqa: E402
from secondorder.scenarios import build_support, handoff  # noqa: E402


def fresh(sid, **kw):
    sc = Scenario(sid, **kw)
    sc.delete()
    return Scenario(sid, **kw)


def test_sally_anne():
    sc = fresh("t_sally", depth=3)
    sc._register("Sally", "Anne")
    sc.enter(["Sally", "Anne"], "room")
    sc.observe("marble", "basket")
    sc.exit("Sally")
    sc.move("Anne", "marble", "box")
    assert sc.resolve([], "marble").value == "box"                 # world
    assert sc.resolve(["Sally"], "marble").value == "basket"       # false belief
    assert sc.resolve(["Anne"], "marble").value == "box"
    assert sc.resolve(["Anne", "Sally"], "marble").value == "basket"  # Anne knows Sally didn't see
    assert sc.resolve(["Sally", "Anne"], "marble").value == "basket"  # Sally thinks Anne still thinks basket
    sc.delete()


def test_copy_on_write_keeps_old_belief_for_absent_child():
    sc = fresh("t_cow", depth=3)
    sc._register("A", "B", "C")
    sc.enter(["A", "B", "C"], "room")
    sc.observe("key", "drawer")
    sc.exit("C")
    sc.move("A", "key", "shelf")
    assert sc.resolve(["A", "B"], "key").value == "shelf"
    assert sc.resolve(["A", "C"], "key").value == "drawer"
    assert sc.resolve(["A", "B", "C"], "key").value == "drawer"
    assert sc.resolve(["A", "C"], "key").via == "witnessed"   # A saw C see the key in the drawer, then C left
    sc.delete()


def test_time_travel():
    sc = fresh("t_tt", depth=2)
    sc._register("A", "B")
    sc.enter(["A", "B"], "room")
    t1 = sc.observe("x", "one")
    sc.move("B", "x", "two")
    assert sc.resolve(["A"], "x", at=t1).value == "one"
    assert sc.resolve(["A"], "x").value == "two"
    sc.delete()


def test_support_handoff_and_acl():
    sc = build_support("t_support")
    fb = tools.false_beliefs("t_support", depth=1)
    assert any(f["chain"] == ["Maya"] and f["entity"] == "refund_4411" for f in fb)
    d = tools.handoff_delta("t_support", "Escalation", "Shipping", about="4411")
    tells = {(f["entity"], f.get("about")) for f in d["facts"]}
    assert ("refund_4411", None) in tells and ("refund_4411", "Maya") in tells
    handoff(sc, "Escalation", "Shipping", d)
    v = AgentView("t_support", "Shipping")
    assert v.resolve(["Shipping", "Maya"], "refund_4411")[0] == "approved"
    assert "refused" in v.try_read_other("Escalation")
    sc.delete()


def test_announcement_creates_common_ground():
    from secondorder.scenarios import build_org
    build_org("t_org")
    p = tools.plan_announcements("t_org", "deploy_freeze", "Asha")
    assert p["plans"]["public_announcement"]["remaining_false_beliefs"] == 0
    assert p["plans"]["private_tells"]["remaining_false_beliefs"] > 0
    Scenario.load("t_org").delete()


def test_acl_view_handles_unicode_names():
    sc = fresh("t_uni", depth=2, trust="credulous")
    sc._register("Tomás", "Zoë")
    sc.enter(["Tomás", "Zoë"], "room")
    sc.say("Zoë", "room", "plan", "A", changes_world=True)
    sc.exit("Tomás")
    sc.say("Zoë", "room", "plan", "B", changes_world=True)
    v = AgentView("t_uni", "Zoë")
    assert v.resolve(["Zoë", "Tomás"], "plan")[0] == "A"
    sc.delete()
