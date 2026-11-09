import pytest
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image

from actuator import HumanActuator
from contract import Gesture
from vision import Frame, FrameFeed
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
    human = HumanActuator(lambda: (1170, 2532))
    human.seen()
    t = threading.Thread(target=human.tap, args=(117, 253.2), daemon=True)
    t.start()
    wait_for(lambda: human.prompt is not None)
    assert human.prompt.say == "Tap here"
    assert human.prompt.gesture.points_norm[0] == pytest.approx((0.1, 0.1))
    assert t.is_alive()
    assert human.done()
    t.join(1)
    assert not t.is_alive() and human.prompt is None


def test_stop_unblocks_human_move():
    stop = threading.Event()
    human = HumanActuator(lambda: (100, 100), stop=stop)
    human.seen()
    errors = []
    t = threading.Thread(target=lambda: errors.append(_raises(lambda: human.swipe(0, 0, 10, 10))), daemon=True)
    t.start()
    wait_for(lambda: human.prompt is not None)
    stop.set()
    t.join(1)
    assert errors == [True] and human.prompt is None


def test_human_without_page_is_unavailable():
    human = HumanActuator(lambda: (100, 100))
    r = human.execute(Gesture("tap", ((0.5, 0.5),)))
    assert (r.ok, r.error) == (False, "device_unavailable")


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

    client = TestClient(create_app(FrameFeed(FakeCapture()), session, FakeAgent))
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
    client = TestClient(create_app(FrameFeed(FakeCapture()), session, lambda: None))
    session.status, session.task, session.steps = "running", "old task", [{"kind": "action", "text": "tap"}]
    assert client.post("/reset").status_code == 409
    session.status = "done"
    assert client.post("/reset").status_code == 200
    assert (session.status, session.task, session.steps) == ("idle", "", [])


def test_done_refused_without_open_move():
    client = TestClient(create_app(FrameFeed(FakeCapture()), Session("gcode"), lambda: None))
    assert client.post("/done").status_code == 400
