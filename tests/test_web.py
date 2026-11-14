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


def test_machine_buttons_home_then_calibrate(tmp_path):
    from actuator import GcodeActuator
    from calib import Calibration
    from calib.run import CalibConfig
    from robot import Machine, RobotConfig
    from web.machine import MachineControl

    class Wire(Machine):
        def send(self, lines):
            self.log += lines

    machine = Wire(RobotConfig(name="m", dry_run=False, home_by_order=True, z_mode="cam"))
    actuator = GcodeActuator(machine, None)
    bot = MachineControl(machine, actuator, CalibConfig(file=str(tmp_path / "c.json")), lambda: None, lambda: 0,
                         "http://192.168.1.5:8765")
    done = Calibration.from_box(100, 200, [10, 10, 70, 150])
    bot._calibrate = lambda: setattr(actuator, "calib", done)
    session = Session("gcode")
    client = TestClient(create_app(FrameFeed(FakeCapture()), session, lambda: None, bot=bot))

    assert client.get("/state").json()["machine"]["homed"] is False
    qr = client.get("/machine/qr.svg")
    assert qr.status_code == 200 and qr.text.lstrip().startswith("<?xml") and "<svg" in qr.text
    assert client.post("/task", json={"task": "go"}).status_code == 409      # not homed, not calibrated
    with pytest.raises(RuntimeError, match="not calibrated"):
        actuator.tap(5, 5)
    assert client.post("/machine/home").status_code == 200
    wait_for(lambda: bot.job is None)
    assert machine.log == ["G28 X Y R0", "M400"]
    assert client.post("/machine/calibrate").status_code == 200
    wait_for(lambda: bot.job is None)
    m = client.get("/state").json()["machine"]
    assert (m["homed"], m["calibrated"], m["screen_box"]) == (True, True, [10, 10, 70, 150])
    # A finished calibration waits for the user's answer before it is saved and used
    assert client.post("/machine/accept").status_code == 409                 # nothing is waiting
    new = Calibration.from_box(100, 200, [20, 20, 80, 160])
    bot.pending = new
    assert client.get("/state").json()["machine"]["pending"] is True
    assert client.post("/machine/reject").status_code == 200
    assert actuator.calib is done and not (tmp_path / "c.json").exists()
    bot.pending = new
    assert client.post("/machine/accept").status_code == 200
    assert actuator.calib is new and (tmp_path / "c.json").exists()
    session.status = "running"
    assert client.post("/machine/home").status_code == 409                   # not while the agent runs
