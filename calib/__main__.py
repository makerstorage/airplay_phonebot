"""Run calibration: uv run python -m calib"""

import time
from pathlib import Path

from calib.run import calibrate, grid_points, load_calib_config
from calib.server import start_server, touch_count
from robot import Machine, load_config
from vision import ScreenCapture, load_vision_config

cfg = load_calib_config()
robot_cfg = load_config()
capture = ScreenCapture(load_vision_config())

if robot_cfg.dry_run:
    print("WARNING: robot.dry_run is true, taps are only printed and no dots will appear.\n")

server, url = start_server(cfg.port)
print(f"1. On the iPhone, open Safari: {url}")
print("2. Start mirroring the iPhone to this Mac. Waiting up to 120 s...")

for _ in range(120):
    try:
        capture.find_window()
        break
    except RuntimeError:
        time.sleep(1)
else:
    raise SystemExit("Mirror window not found.")
time.sleep(3)  # let the mirror settle

machine = Machine(robot_cfg)
machine.connect()
debug = Path("frames")
debug.mkdir(exist_ok=True)

points = grid_points(cfg)
print(f"Tapping {len(points)} points...")
try:
    result = calibrate(machine.tap, lambda: capture.grab().phone, points, cfg.settle_s, debug)
finally:
    machine.close()
    server.shutdown()

result.save(cfg.file)
print(f"\nSaved {cfg.file}. Fit error: {result.error_mm:.2f} mm. Page saw {touch_count()} touches.")
