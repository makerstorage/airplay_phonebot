"""Robot settings = a machine definition (machines/<name>.yaml) + the run settings in config.yaml.

config.yaml:
    robot:
      machine: mks-gen13     # which file in machines/ to use
      dry_run: false         # anything else here overrides the machine file (e.g. port)
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

MACHINES_DIR = Path("machines")


@dataclass
class RobotConfig:
    name: str = "default"
    description: str = ""
    dry_run: bool = True
    port: str = "/dev/tty.usbserial"
    baud: int = 115200
    home_on_start: bool = True
    # True: X/Y are homed only when the user orders it (Home button, --home). Connecting never homes,
    # and taps are refused until the machine was homed in this connection.
    home_by_order: bool = False
    x_max: float = 200
    y_max: float = 200
    # Rough phone screen area in machine mm [x0, y0, x1, y1]. Only a stand-in for dry runs:
    # calibration finds the real screen itself and saves its box in the calibration file.
    screen_box: list[float] = field(default_factory=lambda: [0, 0, 70, 150])
    # How Z moves the stylus. "height": Z goes to z_up / z_touch.
    # "cam": Z turns a cam; half a turn forward = stylus down, the next half turn = back up.
    z_mode: str = "height"
    cam_half_turn: float = 4.0  # Z mm for half a cam turn (cam mode)
    z_up: float = 5.0
    z_touch: float = 0.0
    z_at_connect: float | None = None  # sent as G92 Z on connect (Z of the bed at board reset)
    move_speed: float = 3000
    z_speed: float = 1500
    y_steps_per_mm: float | None = None  # sent as M92 Y on connect (boards without EEPROM forget it)
    z_accel: float | None = None  # mm/s^2, sent as M201 Z on connect
    z_max_speed: float | None = None  # mm/s, sent as M203 Z on connect (lifts the firmware Z speed cap)
    swipe_speed: float = 1500
    fast_swipe_speed: float = 6000
    tap_hold_ms: int = 80
    double_tap_lift: float = 1.0
    dwell_in_seconds: bool = False
    # What the firmware was built with (steps/mm, max speeds, kinematics...). For reference only.
    firmware: dict = field(default_factory=dict)
    # Endstop test results on the real machine. For reference only.
    endstops: dict = field(default_factory=dict)
    # Axis directions checked on the real machine. For reference only.
    directions: dict = field(default_factory=dict)
    # Homing results on the real machine. For reference only.
    homing: dict = field(default_factory=dict)
    # Z cam facts measured on the real machine (e.g. mm_per_turn). For reference only.
    z_cam: dict = field(default_factory=dict)

    @property
    def calib_file(self) -> Path:
        """Each machine has its own calibration: the homography only fits the machine it was measured on."""
        return Path("calibrations") / f"{self.name}.json"


def list_machines(machines_dir: str | Path = MACHINES_DIR) -> list[str]:
    return sorted(p.stem for p in Path(machines_dir).glob("*.yaml"))


def load_machine(name: str, machines_dir: str | Path = MACHINES_DIR) -> dict:
    path = Path(machines_dir) / f"{name}.yaml"
    if not path.exists():
        raise ValueError(f"No machine '{name}'. Known: {', '.join(list_machines(machines_dir)) or 'none'}")
    data = yaml.safe_load(path.read_text()) or {}
    data["name"] = name
    return data


def load_config(path: str | Path = "config.yaml", machine: str | None = None,
                machines_dir: str | Path = MACHINES_DIR) -> RobotConfig:
    """`machine` overrides robot.machine from config.yaml (for --machine on the command line)."""
    robot = dict((yaml.safe_load(Path(path).read_text()) or {}).get("robot", {}))
    name = machine or robot.pop("machine", None)
    robot.pop("machine", None)
    if not name:
        raise ValueError(f"Set robot.machine in {path}. Known machines: {', '.join(list_machines(machines_dir))}")
    return RobotConfig(**{**load_machine(name, machines_dir), **robot})
