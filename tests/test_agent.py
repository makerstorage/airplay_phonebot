from types import SimpleNamespace as NS

import pytest
from PIL import Image

from actuator import GcodeActuator
from agent import Agent, AgentConfig, PhoneEnv
from agent.loop import NOT_EXECUTED, TOOLS
from agent.skills import Skill
from calib import Calibration
from robot import Machine, RobotConfig
from vision import Frame

BOX = [10, 20, 80, 170]  # machine mm


class FakeCapture:
    def __init__(self):
        self.frame = Frame.from_phone(Image.new("RGB", (1170, 2532), "white"), 1280)

    def grab(self):
        return self.frame


@pytest.fixture
def env():
    machine = Machine(RobotConfig(dry_run=True, home_on_start=False))
    calib = Calibration.from_box(1170, 2532, BOX)
    return PhoneEnv(FakeCapture(), GcodeActuator(machine, calib), settle_s=0, stable_timeout_s=0, sleep=lambda s: None)


def moves(env):
    return [l for l in env.actuator.machine.log if l.startswith(("G0", "G1 X"))]


def test_tap_maps_model_pixels_to_machine_mm(env):
    w, h = env.size  # 591x1280 model pixels
    env.tap(w / 2, h / 2)
    assert moves(env) == ["G0 X45.00 Y95.00 F3000"]


def test_scroll_down_swipes_finger_up(env):
    env.scroll("down", 3)
    start, end = moves(env)
    y_start = float(start.split("Y")[1].split()[0])
    y_end = float(end.split("Y")[1].split()[0])
    assert y_start > y_end


def test_long_press_with_mouse_down_up(env):
    env.cursor = (100, 200)
    env.press()
    env.release()
    log = env.actuator.machine.log
    assert log.index("G1 Z0.00 F1500") < log.index("G1 Z5.00 F1500", log.index("G1 Z0.00 F1500"))
    assert env.pen_down is False


def test_tap_outside_screen_refused(env):
    with pytest.raises(ValueError):
        env.tap(5000, 10)


def test_toolset_disables_keyboard_actions():
    toolset = TOOLS[0]
    assert toolset["type"] == "computer_toolset_20260801"
    assert toolset["configs"]["type"] == {"enabled": False}


# Agent loop with a scripted model


def tool_use(id, name, inp, computer=True):
    return NS(type="tool_use", id=id, name=name, input=inp, toolset_name="computer" if computer else None)


def response(*blocks, stop="tool_use"):
    return NS(content=list(blocks), stop_reason=stop, usage=None)


def make_agent(env, script):
    agent = Agent(None, AgentConfig(), env, {"ios_basics": Skill("ios_basics", "d", "BODY")}, ask=lambda q: "yes")
    calls = iter(script)
    agent._call = lambda messages: next(calls)
    return agent


def test_batch_stops_at_first_failure(env):
    agent = make_agent(env, [
        response(
            tool_use("a", "left_click", {"coordinate": [100, 100]}),
            tool_use("b", "left_click", {"coordinate": [9999, 100]}),
            tool_use("c", "left_click", {"coordinate": [200, 200]}),
        ),
        response(NS(type="text", text="done"), stop="end_turn"),
    ])
    assert agent.run("task") == "done"

    results = agent.messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b", "c"]
    assert all(r["toolset_name"] == "computer" for r in results)
    assert results[1]["is_error"] and "outside the screen" in results[1]["content"]
    assert results[2] == {"type": "tool_result", "tool_use_id": "c", "toolset_name": "computer",
                          "content": NOT_EXECUTED, "is_error": True}
    # The fresh screenshot rides on the last successful result
    assert [b["type"] for b in results[0]["content"]] == ["text", "image"]
    assert len(moves(env)) == 1  # only the first tap ran


def test_custom_tools_and_final_answer(env):
    events = []
    agent = make_agent(env, [
        response(
            tool_use("t", "todo", {"items": [{"text": "open app", "status": "in_progress"}]}, computer=False),
            tool_use("s", "load_skill", {"name": "ios_basics"}, computer=False),
            tool_use("q", "ask_user", {"question": "Order it?"}, computer=False),
        ),
        response(NS(type="text", text="Ordered."), stop="end_turn"),
    ])
    agent.emit = lambda kind, data: events.append(kind)
    assert agent.run("order pizza") == "Ordered."

    results = agent.messages[2]["content"]
    assert "toolset_name" not in results[0]
    assert results[1]["content"] == "BODY"
    assert results[2]["content"] == "User answered: yes"
    assert {"plan", "ask", "answer", "done"} <= set(events)


def test_stop_event_ends_run(env):
    agent = make_agent(env, [])
    agent.stop.set()
    assert agent.run("task") == "Stopped by the user."
