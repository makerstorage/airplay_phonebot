"""Gesture demo: uv run python -m robot [--machine NAME]
Moves the real machine unless robot.dry_run is true."""

import argparse

from robot import Machine, load_config

parser = argparse.ArgumentParser()
parser.add_argument("--machine", help="machine file in machines/ (overrides robot.machine)")
args = parser.parse_args()

cfg = load_config(machine=args.machine)
print(f"# machine {cfg.name}: {cfg.description} ({'dry run' if cfg.dry_run else cfg.port})")
m = Machine(cfg)
m.connect()
print("# tap")
m.tap(50, 80)
print("# long press")
m.long_press(60, 90, ms=1000)
print("# swipe")
m.swipe(50, 150, 50, 50)
m.close()
