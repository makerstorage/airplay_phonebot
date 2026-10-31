"""Runs computer-use actions on the real iPhone.

Claude sees the downscaled mirror image ("model pixels"). Each coordinate goes
model pixel -> phone pixel (Frame) -> Actuator (the G-code machine, or a person by hand).
"""

import base64
import io
import time
from typing import Callable, Protocol

import numpy as np
from PIL import Image

from actuator import Actuator
from vision import Frame


class FrameSource(Protocol):
    def grab(self) -> Frame: ...


class PhoneEnv:
    def __init__(
        self,
        capture: FrameSource,
        actuator: Actuator,
        settle_s: float = 0.6,
        stable_timeout_s: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.capture = capture
        self.actuator = actuator
        self.settle_s = settle_s
        self.stable_timeout_s = stable_timeout_s
        self.sleep = sleep
        self.frame = capture.grab()
        self.cursor = (self.frame.model.width // 2, self.frame.model.height // 2)
        self.pen_down = False
        self._last_action = 0.0

    # Screen

    @property
    def size(self) -> tuple[int, int]:
        return self.frame.model.size

    def screenshot(self) -> Image.Image:
        """Waits for the mirror to catch up and animations to stop, then returns the model image."""
        wait = self.settle_s - (time.monotonic() - self._last_action)
        if wait > 0:
            self.sleep(wait)
        frame = self.capture.grab()
        deadline = time.monotonic() + self.stable_timeout_s
        while time.monotonic() < deadline:
            self.sleep(0.3)
            nxt = self.capture.grab()
            if _changed(frame.model, nxt.model) < 1.5:
                frame = nxt
                break
            frame = nxt
        self.frame = frame
        return frame.model

    def zoom(self, region: list[float]) -> Image.Image:
        x0, y0, x1, y1 = region
        self._check(x0, y0)
        self._check(x1, y1)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("zoom region must have x1 > x0 and y1 > y0")
        p0 = self.frame.to_phone(x0, y0)
        p1 = self.frame.to_phone(x1, y1)
        crop = self.frame.phone.crop((*map(round, p0), *map(round, p1)))
        # Fit the crop into the usual screenshot size
        w, h = self.size
        scale = min(w / crop.width, h / crop.height)
        return crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)

    # Actions (model pixels in, phone pixels out to the actuator)

    def tap(self, x: float, y: float) -> None:
        self._release_if_down()
        self.actuator.tap(*self._to_phone(x, y))
        self._moved(x, y)

    def double_tap(self, x: float, y: float) -> None:
        self._release_if_down()
        self.actuator.double_tap(*self._to_phone(x, y))
        self._moved(x, y)

    def swipe(self, x1: float, y1: float, x2: float, y2: float, fast: bool = False) -> None:
        self._release_if_down()
        self.actuator.swipe(*self._to_phone(x1, y1), *self._to_phone(x2, y2), fast)
        self._moved(x2, y2)

    def scroll(self, direction: str, amount: int, at: tuple[float, float] | None = None) -> None:
        # Scrolling "down" shows content further down, so the finger moves up
        w, h = self.size
        cx, cy = at or (w / 2, h / 2)
        horizontal = direction in ("left", "right")
        span = w if horizontal else h
        dist = min(max(amount, 1) * 0.08 * span, 0.6 * span)
        sign = 1 if direction in ("down", "right") else -1
        if horizontal:
            x1, x2 = cx + sign * dist / 2, cx - sign * dist / 2
            x1, x2 = (min(max(v, 0.05 * w), 0.95 * w) for v in (x1, x2))
            self.swipe(x1, cy, x2, cy)
        else:
            y1, y2 = cy + sign * dist / 2, cy - sign * dist / 2
            y1, y2 = (min(max(v, 0.05 * h), 0.95 * h) for v in (y1, y2))
            self.swipe(cx, y1, cx, y2)

    def move(self, x: float, y: float) -> None:
        # With the stylus down this drags on the screen; with it up it just hovers
        if self.pen_down:
            self.actuator.drag_to(*self._to_phone(x, y))
        self._moved(x, y)

    def press(self) -> None:
        if not self.pen_down:
            self.actuator.press(*self._to_phone(*self.cursor))
            self.pen_down = True
            self._last_action = time.monotonic()

    def release(self) -> None:
        if self.pen_down:
            self.actuator.release()
            self.pen_down = False
            self._last_action = time.monotonic()

    def home(self) -> None:
        # iPhone 13 Pro home gesture: quick swipe up from the bottom edge
        w, h = self.size
        self.swipe(w / 2, h * 0.995, w / 2, h * 0.6, fast=True)

    # Helpers

    def _to_phone(self, x: float, y: float) -> tuple[float, float]:
        self._check(x, y)
        return self.frame.to_phone(x, y)

    def _check(self, x: float, y: float) -> None:
        w, h = self.size
        if not (0 <= x <= w and 0 <= y <= h):
            raise ValueError(f"Coordinate ({x}, {y}) is outside the screen ({w}x{h})")

    def _moved(self, x: float, y: float) -> None:
        self.cursor = (x, y)
        self._last_action = time.monotonic()

    def _release_if_down(self) -> None:
        if self.pen_down:
            self.release()


def _changed(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute pixel difference on a small grayscale copy."""
    size = (64, 128)
    x = np.asarray(a.convert("L").resize(size), dtype=np.int16)
    y = np.asarray(b.convert("L").resize(size), dtype=np.int16)
    return float(np.abs(x - y).mean())


def image_block(img: Image.Image) -> dict:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.standard_b64encode(buf.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
