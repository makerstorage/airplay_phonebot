"""uv run python -m vision             -> save one frame to frames/
   uv run python -m vision --delay 15  -> wait 15 s first (time to start mirroring)
   uv run python -m vision --list      -> list on-screen windows
   uv run python -m vision --watch     -> wait for the mirror window to appear, save it and its app name"""

import sys
import time
from pathlib import Path

from vision import ScreenCapture, list_windows, load_vision_config

if "--delay" in sys.argv:
    delay = int(sys.argv[sys.argv.index("--delay") + 1])
    print(f"Waiting {delay} s, start mirroring now...")
    time.sleep(delay)

if "--list" in sys.argv:
    for w in list_windows():
        b = w["bounds"]
        print(f"{w['id']:>6}  {w['owner']:<25} {w['name']!r:<40} {b['Width']:.0f}x{b['Height']:.0f}")
    sys.exit()

out = Path("frames")
out.mkdir(exist_ok=True)
cfg = load_vision_config()

if "--watch" in sys.argv:
    before = {w["id"] for w in list_windows()}
    print("Watching for 120 s, start mirroring now...")
    for _ in range(120):
        time.sleep(1)
        new = [w for w in list_windows() if w["id"] not in before
               and w["bounds"]["Width"] * w["bounds"]["Height"] > 200_000]
        if new:
            w = max(new, key=lambda w: w["bounds"]["Width"] * w["bounds"]["Height"])
            time.sleep(3)  # let the mirror image settle
            cfg.window_owner = w["owner"]
            (out / "window.txt").write_text(f"owner: {w['owner']}\nname: {w['name']}\nbounds: {w['bounds']}\n")
            break
    else:
        sys.exit("No new window appeared.")

frame = ScreenCapture(cfg).grab()
frame.phone.save(out / "phone.png")
frame.model.save(out / "model.png")
print(f"phone {frame.phone.size}, model {frame.model.size}, scale {frame.scale:.3f} -> saved to frames/")
