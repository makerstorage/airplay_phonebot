"""A person does the moves by hand: each move is shown (on the web page) and waits for Done."""

import threading
from typing import Callable

from actuator.base import Intent


class HumanActuator:
    def __init__(self, show: Callable[[Intent | None], None], stop: threading.Event | None = None):
        self.show = show  # called with the move to do, then with None when it's done
        self.stop = stop or threading.Event()
        self._done = threading.Event()

    def done(self) -> None:
        """The person finished the shown move (the web page's Done button)."""
        self._done.set()

    def tap(self, x: float, y: float) -> None:
        self._do(Intent("tap", [(x, y)], "Tap here"))

    def double_tap(self, x: float, y: float) -> None:
        self._do(Intent("double_tap", [(x, y)], "Double tap here"))

    def swipe(self, x1: float, y1: float, x2: float, y2: float, fast: bool = False) -> None:
        self._do(Intent("swipe", [(x1, y1), (x2, y2)], "Quick flick along the arrow" if fast else "Swipe along the arrow"))

    def press(self, x: float, y: float) -> None:
        self._do(Intent("press", [(x, y)], "Press here and keep holding"))

    def drag_to(self, x: float, y: float) -> None:
        self._do(Intent("drag", [(x, y)], "Keep holding and move here"))

    def release(self) -> None:
        self._do(Intent("release", [], "Lift your finger"))

    def _do(self, intent: Intent) -> None:
        self._done.clear()
        self.show(intent)
        try:
            while not self._done.wait(0.2):
                if self.stop.is_set():
                    raise RuntimeError("Stopped by the user")
        finally:
            self.show(None)
