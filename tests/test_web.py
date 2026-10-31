import threading
import time

from fastapi.testclient import TestClient
from PIL import Image

from actuator import HumanActuator
from vision import Frame
from web.server import Session, create_app


class FakeCapture:
    def grab(self):
        return Frame.from_phone(Image.new("RGB", (1170, 2532), "white"), 1280)


def wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_human_tap_waits_for_done():
    session = Session("human")
    human = HumanActuator(session.show_intent, session.stop)
    t = threading.Thread(target=human.tap, args=(100, 200))
    t.start()
    wait_for(lambda: session.intent is not None)
    assert session.state()["intent"] == {"kind": "tap", "points": [(100, 200)], "text": "Tap here"}
    assert t.is_alive()
    human.done()
    t.join(1)
    assert not t.is_alive() and session.intent is None


def test_stop_unblocks_human_move():
    session = Session("human")
    human = HumanActuator(session.show_intent, session.stop)
    errors = []
    t = threading.Thread(target=lambda: errors.append(_raises(lambda: human.swipe(0, 0, 10, 10))))
    t.start()
    wait_for(lambda: session.intent is not None)
    session.stop.set()
    t.join(1)
    assert errors == [True] and session.intent is None


def _raises(fn):
    try:
        fn()
    except RuntimeError:
        return True
    return False


def test_task_runs_agent_and_answers_question():
    session = Session("human")

    class FakeAgent:
        def run(self, task):
            session.on_event("plan", {"items": [{"text": "step", "status": "in_progress"}]})
            answer = session.ask("Sure?")
            session.on_event("done", {"text": f"{task}: {answer}"})

    client = TestClient(create_app(FakeCapture(), session, FakeAgent))
    assert client.post("/task", json={"task": "go"}).status_code == 200
    wait_for(lambda: session.question == "Sure?")
    assert client.post("/task", json={"task": "again"}).status_code == 409
    client.post("/answer", json={"text": "yes"})
    wait_for(lambda: session.status == "done")
    state = client.get("/state").json()
    assert state["plan"][0]["text"] == "step"
    assert state["steps"][-1] == {"kind": "done", "text": "go: yes", "t": state["steps"][-1]["t"]}


def test_reset_clears_session_but_not_while_running():
    session = Session("gcode")
    client = TestClient(create_app(FakeCapture(), session, lambda: None))
    session.status, session.task, session.steps = "running", "old task", [{"kind": "action", "text": "tap"}]
    assert client.post("/reset").status_code == 409
    session.status = "done"
    assert client.post("/reset").status_code == 200
    assert (session.status, session.task, session.steps) == ("idle", "", [])


def test_done_refused_in_gcode_mode():
    client = TestClient(create_app(FakeCapture(), Session("gcode"), lambda: None))
    assert client.post("/done").status_code == 400
