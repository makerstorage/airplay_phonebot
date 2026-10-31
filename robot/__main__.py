"""Dry-run demo: uv run python -m robot"""

from robot import Machine, load_config

cfg = load_config()
m = Machine(cfg)
m.connect()
print("# tap")
m.tap(50, 80)
print("# long press")
m.long_press(60, 90, ms=1000)
print("# swipe")
m.swipe(50, 150, 50, 50)
m.close()
