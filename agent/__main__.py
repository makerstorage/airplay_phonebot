"""Run a task from the terminal:
   uv run python -m agent "open Settings and turn on dark mode"
   uv run python -m agent --image frames/phone.png "..."   (static screen, for testing without mirroring)
"""

import argparse
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image

from actuator import GcodeActuator, HumanActuator, load_actuator_mode
from agent import Agent, PhoneEnv, load_agent_config, load_skills
from calib import Calibration
from calib.run import load_calib_config
from robot import Machine, load_config
from vision import Frame, ScreenCapture, load_vision_config


class StaticCapture:
    """Always returns the same phone image."""

    def __init__(self, path: str, max_long_edge: int):
        self.frame = Frame.from_phone(Image.open(path).convert("RGB"), max_long_edge)

    def grab(self) -> Frame:
        return self.frame


def print_event(kind: str, data: dict) -> None:
    if kind == "screenshot":
        return
    if kind == "action":
        print(f"  -> {data['name']} {data['input']}")
    elif kind == "plan":
        for item in data["items"]:
            mark = {"done": "x", "in_progress": ">"}.get(item["status"], " ")
            print(f"  [{mark}] {item['text']}")
    elif kind == "usage":
        print(f"  (tokens in {data['input']}, out {data['output']}, cached {data['cache_read']})")
    else:
        print(f"[{kind}] {next(iter(data.values()), '')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--image", help="use a static phone screenshot instead of the mirror")
    parser.add_argument("--max-steps", type=int, help="override agent.max_steps")
    args = parser.parse_args()

    load_dotenv()  # ANTHROPIC_API_KEY from .env
    cfg = load_agent_config()
    if args.max_steps:
        cfg.max_steps = args.max_steps
    robot_cfg = load_config()
    vision_cfg = load_vision_config()
    calib_cfg = load_calib_config()

    if args.image and not robot_cfg.dry_run:
        sys.exit("--image only works with robot.dry_run: true")
    capture = StaticCapture(args.image, vision_cfg.max_long_edge) if args.image else ScreenCapture(vision_cfg)

    frame = capture.grab()
    if Path(calib_cfg.file).exists():
        calib = Calibration.load(calib_cfg.file)
    elif robot_cfg.dry_run:
        print(f"No {calib_cfg.file}: dry run maps the screen onto screen_box.")
        calib = Calibration.from_box(*frame.phone.size, calib_cfg.screen_box)
    else:
        sys.exit(f"No {calib_cfg.file}. Run `uv run python -m calib` first.")

    machine = Machine(robot_cfg)
    if load_actuator_mode() == "human":
        def show(intent):
            if intent:
                points = ", ".join(f"({x:.0f}, {y:.0f})" for x, y in intent.points)
                input(f"\n  DO: {intent.text} {points} (phone pixels), then press Enter ")
                actuator.done()
        actuator = HumanActuator(show)
    else:
        machine.connect()
        actuator = GcodeActuator(machine, calib)
    env = PhoneEnv(capture, actuator, cfg.settle_s, cfg.stable_timeout_s)
    agent = Agent(
        anthropic.Anthropic(),
        cfg,
        env,
        load_skills(cfg.skills_dir),
        ask=lambda q: input(f"\n{q}\n> "),
        on_event=print_event,
    )
    try:
        agent.run(args.task)
    finally:
        machine.close()


if __name__ == "__main__":
    main()
