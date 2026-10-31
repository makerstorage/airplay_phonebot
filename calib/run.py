"""Calibration: tap known machine points, find the dots in the mirror, fit the homography."""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import yaml
from PIL import Image

from calib.detect import find_new_dot
from calib.homography import Calibration, apply_homography, fit_homography


@dataclass
class CalibConfig:
    port: int = 8765
    # Rough phone screen area in machine mm [x0, y0, x1, y1]; taps stay inside it
    screen_box: list[float] = field(default_factory=lambda: [0, 0, 70, 150])
    grid: int = 3          # grid x grid taps
    margin: float = 0.15   # keep taps this fraction away from the box edges
    settle_s: float = 1.0  # wait for the AirPlay image to update after a tap
    file: str = "calib.json"


def load_calib_config(path: str | Path = "config.yaml") -> CalibConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return CalibConfig(**data.get("calib", {}))


def grid_points(cfg: CalibConfig) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = cfg.screen_box
    mx, my = (x1 - x0) * cfg.margin, (y1 - y0) * cfg.margin
    xs = np.linspace(x0 + mx, x1 - mx, cfg.grid)
    ys = np.linspace(y0 + my, y1 - my, cfg.grid)
    return [(float(x), float(y)) for y in ys for x in xs]


def calibrate(
    tap: Callable[[float, float], None],
    grab: Callable[[], Image.Image],
    points: list[tuple[float, float]],
    settle_s: float = 1.0,
    debug_dir: Path | None = None,
) -> Calibration:
    pixels, machine = [], []
    for i, (mx, my) in enumerate(points):
        before = grab()
        tap(mx, my)
        time.sleep(settle_s)
        after = grab()
        dot = find_new_dot(before, after)
        if debug_dir:
            after.save(debug_dir / f"calib_{i}.png")
        if dot is None:
            print(f"  point {i + 1}/{len(points)} ({mx:.1f}, {my:.1f}) mm: no dot found")
            continue
        print(f"  point {i + 1}/{len(points)} ({mx:.1f}, {my:.1f}) mm -> pixel ({dot[0]:.0f}, {dot[1]:.0f})")
        pixels.append(dot)
        machine.append((mx, my))

    if len(pixels) < 4:
        raise RuntimeError(f"Only {len(pixels)} dots found, need 4 or more")

    h = fit_homography(pixels, machine)
    errors = [np.hypot(*np.subtract(apply_homography(h, *p), m)) for p, m in zip(pixels, machine)]
    return Calibration(h, error_mm=float(np.sqrt(np.mean(np.square(errors)))))
