from pathlib import Path

import yaml


def load_actuator_mode(path: str | Path = "config.yaml") -> str:
    data = yaml.safe_load(Path(path).read_text()) or {}
    mode = (data.get("actuator") or {}).get("mode", "human")
    if mode not in ("human", "gcode"):
        raise ValueError(f"actuator.mode must be 'human' or 'gcode', not '{mode}'")
    return mode
