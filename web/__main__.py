"""uv run python -m web                -> control page at http://localhost:8000
   uv run python -m web --mode human   -> override actuator.mode (human = you tap; never connects the machine)

Start UxPlay first (~/Code/UxPlay/build/uxplay -n Phonebot -nh -vsync no),
then on the iPhone/iPad: Control Center > Screen Mirroring > Phonebot.
actuator.mode in config.yaml picks who taps for the agent: human (you, from the page) or gcode (the machine).
Teaching (the Teach tab) always uses you as the actuator."""

import argparse
import sys
from pathlib import Path

import anthropic
import uvicorn
import yaml
from dotenv import load_dotenv

from actuator import GcodeActuator, HumanActuator, load_actuator_mode
from agent import Agent, PhoneEnv, load_agent_config, load_skills
from calib import Calibration
from calib.run import load_calib_config
from robot import Machine, load_config
from teach import TeachController, load_teach_config
from vision import FrameFeed, ScreenCapture, load_vision_config
from web.server import Session, create_app

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["human", "gcode"], help="override actuator.mode from config.yaml")
parser.add_argument("--port", type=int, help="override web.port from config.yaml")
args = parser.parse_args()

load_dotenv()  # ANTHROPIC_API_KEY from .env
web_cfg = (yaml.safe_load(Path("config.yaml").read_text()) or {}).get("web", {})
mode = args.mode or load_actuator_mode()
agent_cfg = load_agent_config()
teach_cfg = load_teach_config()
capture = ScreenCapture(load_vision_config())
feed = FrameFeed(capture, fps=web_cfg.get("fps", 5))
feed.start()
session = Session(mode)


def screen_size() -> tuple[int, int]:
    f = feed.latest()
    if f is None:
        raise RuntimeError("No picture of the phone yet")
    return f.size


human = HumanActuator(screen_size)

if mode == "human":
    actuator = human
else:
    calib_cfg = load_calib_config()
    if not Path(calib_cfg.file).exists():
        sys.exit(f"No {calib_cfg.file}. Run `uv run python -m calib` first, or use --mode human.")
    machine = Machine(load_config())
    machine.connect()
    actuator = GcodeActuator(machine, Calibration.load(calib_cfg.file))

client = anthropic.Anthropic()


def new_agent() -> Agent:
    env = PhoneEnv(capture, actuator, agent_cfg.settle_s, agent_cfg.stable_timeout_s)
    return Agent(client, agent_cfg, env, load_skills(agent_cfg.skills_dir), ask=session.ask,
                 on_event=session.on_event, stop=session.stop)


teach = TeachController(feed, human, teach_cfg, lambda: client, agent_running=lambda: session.status == "running")
app = create_app(feed, session, new_agent, human, teach, web_cfg.get("fps", 5))
port = args.port or web_cfg.get("port", 8000)
print(f"Mode: {mode}. Open http://localhost:{port}")
uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
