"""Does the moves with the G-code machine: phone pixel -> machine mm (Calibration) -> G-code."""

from calib import Calibration
from robot import Machine


class GcodeActuator:
    def __init__(self, machine: Machine, calib: Calibration | None):
        """calib None = not calibrated yet: every move is refused until `calib` is set."""
        self.machine = machine
        self.calib = calib

    def tap(self, x: float, y: float) -> None:
        self.machine.tap(*self._mm(x, y))

    def double_tap(self, x: float, y: float) -> None:
        self.machine.double_tap(*self._mm(x, y))

    def swipe(self, x1: float, y1: float, x2: float, y2: float, fast: bool = False) -> None:
        speed = self.machine.cfg.fast_swipe_speed if fast else None
        self.machine.swipe(*self._mm(x1, y1), *self._mm(x2, y2), speed)

    def press(self, x: float, y: float) -> None:
        self.machine.press(*self._mm(x, y))

    def drag_to(self, x: float, y: float) -> None:
        self.machine.drag_to(*self._mm(x, y))

    def release(self) -> None:
        self.machine.release()

    def _mm(self, x: float, y: float) -> tuple[float, float]:
        if self.calib is None:
            raise RuntimeError("The machine is not calibrated. Calibrate it first (control page).")
        return self.calib.to_machine(x, y)
