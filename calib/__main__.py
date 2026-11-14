"""Run calibration from the terminal: uv run python -m calib --home [--machine NAME]
Saves calibrations/<machine>.json. (The control page has a Calibrate button that does the same.)

Connecting resets the board, so on a home_by_order machine the position is unknown: --home homes X/Y first."""

import argparse
import time
from pathlib import Path

from calib import Calibration
from calib.run import box_center, calibrate, check_summary, load_calib_config
from calib.server import page_info, set_view, start_server, touch_points
from robot import Machine, load_config
from vision import ScreenCapture, load_vision_config

parser = argparse.ArgumentParser()
parser.add_argument("--machine", help="machine file in machines/ (overrides robot.machine)")
parser.add_argument("--home", action="store_true", help="home X/Y after connecting (never Z)")
args = parser.parse_args()

robot_cfg = load_config(machine=args.machine)
cfg = load_calib_config(robot_cfg)
print(f"Machine: {robot_cfg.name} ({robot_cfg.description})")
if robot_cfg.home_by_order and not args.home and not robot_cfg.dry_run:
    raise SystemExit("Connecting resets the board and the position is lost. "
                     "Run with --home to home X/Y first, or calibrate from the control page.")
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
last = Calibration.load(cfg.file) if Path(cfg.file).exists() else None

try:
    if args.home:
        print("Homing X/Y...")
        machine.home()
    result = calibrate(machine.tap, lambda: capture.grab().phone, touch_points, robot_cfg.x_max, robot_cfg.y_max,
                       cfg, seed=box_center(last.screen_box) if last else None, debug_dir=debug, show=set_view, page=page_info)
finally:
    machine.close()

print(f"\n{check_summary(result.check)}. Look at the dots on the iPhone.")
for t in result.check["targets"]:
    off = f"{t['err_mm']:.1f} mm off" if t["err_mm"] is not None else t["state"]
    print(f"  target at pixel ({t['px'][0]:.0f}, {t['px'][1]:.0f}): {off}")
ok = input("Is it OK? [y/N] ").strip().lower() == "y"
server.shutdown()
if not ok:
    raise SystemExit("Not saved.")
Path(cfg.file).parent.mkdir(exist_ok=True)
result.save(cfg.file)
print(f"\nSaved {cfg.file}. Fit error: {result.error_mm:.2f} mm. Screen box: {result.screen_box} mm.")
