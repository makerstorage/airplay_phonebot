from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class RobotConfig:
    dry_run: bool = True
    port: str = "/dev/tty.usbserial"
    baud: int = 115200
    home_on_start: bool = True
    x_max: float = 200
    y_max: float = 200
    z_up: float = 5.0
    z_touch: float = 0.0
    z_at_connect: float | None = None  # sent as G92 Z on connect (Z of the bed at board reset)
    move_speed: float = 3000
    z_speed: float = 1500
    z_accel: float | None = None  # mm/s^2, sent as M201 Z on connect
    swipe_speed: float = 1500
    fast_swipe_speed: float = 6000
    tap_hold_ms: int = 80
    double_tap_lift: float = 1.0
    dwell_in_seconds: bool = False


def load_config(path: str | Path = "config.yaml") -> RobotConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return RobotConfig(**data.get("robot", {}))
