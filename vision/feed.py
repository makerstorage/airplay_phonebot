"""One background thread grabs the mirror; the live stream and the teaching recorder read from it.

Each new picture gets a `seq`. A window capture returns a picture even when nothing changed, so the feed
compares each picture with the previous one and remembers when the screen last changed: `settled()` uses it.
"""

import io
import threading
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from contract import Health


@dataclass
class FeedFrame:
    seq: int
    t: float             # time.time() it was captured
    image: Image.Image   # phone image, full resolution, cropped to the screen
    _jpeg: bytes | None = field(default=None, repr=False)

    @property
    def jpeg(self) -> bytes:
        if self._jpeg is None:
            buf = io.BytesIO()
            self.image.save(buf, "JPEG", quality=80)
            self._jpeg = buf.getvalue()
        return self._jpeg

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


def screen_diff(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute grey difference on a small copy (0..255). Ignores tiny changes like the clock."""
    size = (64, 128) if a.height >= a.width else (128, 64)
    x = np.asarray(a.convert("L").resize(size), dtype=np.int16)
    y = np.asarray(b.convert("L").resize(size), dtype=np.int16)
    return float(np.abs(x - y).mean())


class FrameFeed:
    def __init__(self, capture, fps: float = 5, change_threshold: float = 1.5):
        self.capture = capture  # anything with grab() -> vision.Frame
        self.interval = 1 / fps
        self.threshold = change_threshold
        self._latest: FeedFrame | None = None
        self._last_change = 0.0      # time.monotonic() of the last visible change
        self._error = "not started"
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="frame-feed")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> FeedFrame | None:
        return self._latest

    def wait_newer(self, after_seq: int, timeout: float) -> FeedFrame | None:
        with self._cond:
            self._cond.wait_for(lambda: self._latest and self._latest.seq > after_seq, timeout)
            f = self._latest
        return f if f and f.seq > after_seq else None

    def settled(self, quiet: float = 0.6, most: float = 4.0, since: float | None = None) -> FeedFrame | None:
        """Waits until the screen has not changed for `quiet` s (counted from `since`, default now), at most
        `most` s, and returns the latest frame."""
        start = time.monotonic() if since is None else since
        end = time.monotonic() + most
        while time.monotonic() < end:
            calm_from = max(self._last_change, start)
            if time.monotonic() - calm_from >= quiet and self._latest:
                break
            time.sleep(0.05)
        return self._latest

    def last_change(self) -> float:
        return self._last_change

    def health(self) -> Health:
        f = self._latest
        if f is None or time.time() - f.t > 3:
            return Health("down", self._error or "no picture yet")
        return Health("ok")

    # Thread

    def _run(self) -> None:
        seq = 0
        while not self._stop.is_set():
            start = time.monotonic()
            try:
                img = self.capture.grab().phone
                self._error = ""
            except Exception as err:  # no mirror window yet
                self._error = str(err)
                time.sleep(1)
                continue
            prev = self._latest
            if prev is None or prev.size != img.size or screen_diff(prev.image, img) > self.threshold:
                self._last_change = time.monotonic()
            seq += 1
            with self._cond:
                self._latest = FeedFrame(seq, time.time(), img)
                self._cond.notify_all()
            time.sleep(max(0.0, self.interval - (time.monotonic() - start)))
