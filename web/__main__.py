"""uv run python -m web  -> control page at http://localhost:8000

Start UxPlay first (~/Code/UxPlay/build/uxplay -n Phonebot -nh -vsync no),
then on the iPhone: Control Center > Screen Mirroring > Phonebot.
actuator.mode in config.yaml picks who taps: human (you, from the page) or gcode (the machine)."""

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
from vision import ScreenCapture, load_vision_config
from web.server import Session, create_app

load_dotenv()  # ANTHROPIC_API_KEY from .env
web_cfg = (yaml.safe_load(Path("config.yaml").read_text()) or {}).get("web", {})
mode = load_actuator_mode()
agent_cfg = load_agent_config()
capture = ScreenCapture(load_vision_config())
session = Session(mode)

if mode == "human":
    actuator = HumanActuator(session.show_intent, session.stop)
    done = actuator.done
else:
    calib_cfg = load_calib_config()
    if not Path(calib_cfg.file).exists():
        sys.exit(f"No {calib_cfg.file}. Run `uv run python -m calib` first, or set actuator.mode: human.")
    machine = Machine(load_config())
    machine.connect()
    actuator = GcodeActuator(machine, Calibration.load(calib_cfg.file))
    done = None

client = anthropic.Anthropic()
skills = load_skills(agent_cfg.skills_dir)


def new_agent() -> Agent:
    env = PhoneEnv(capture, actuator, agent_cfg.settle_s, agent_cfg.stable_timeout_s)
    return Agent(client, agent_cfg, env, skills, ask=session.ask, on_event=session.on_event, stop=session.stop)


app = create_app(capture, session, new_agent, done, web_cfg.get("fps", 5))
print(f"Mode: {mode}. Open http://localhost:{web_cfg.get('port', 8000)}")
uvicorn.run(app, host="0.0.0.0", port=web_cfg.get("port", 8000), log_level="warning")
