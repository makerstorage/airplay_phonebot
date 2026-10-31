"""Probe: is the iPhone visible over USB? uv run python scratch_probe_usb.py"""

import time

from vision.usb import UsbCapture, find_iphone

dev = find_iphone()
print("device:", dev.localizedName() if dev else None)
if dev:
    cap = UsbCapture()
    frame = cap.grab()
    time.sleep(1)
    frame = cap.grab()
    frame.phone.save("frames/usb.png")
    print("frame", frame.phone.size, "-> frames/usb.png")
    cap.stop()
