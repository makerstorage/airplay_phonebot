"""Sends G-code to the machine, or prints it in dry-run mode."""

from robot.config import RobotConfig
from robot.gcode import GcodeBuilder


class Machine:
    def __init__(self, cfg: RobotConfig):
        self.cfg = cfg
        self.gcode = GcodeBuilder(cfg)
        self.log: list[str] = []  # every line sent, for the UI and tests
        self._serial = None

    def connect(self) -> None:
        if not self.cfg.dry_run:
            import serial

            self._serial = serial.Serial(self.cfg.port, self.cfg.baud, timeout=30)
            self._serial.reset_input_buffer()
            if not self.cfg.home_on_start and self.position() == (0.0, 0.0, 0.0):
                # Without homing, the position only lives in the board (set by hand with G92)
                self.close()
                raise RuntimeError("Board reports X0 Y0 Z0: it was reset and the position is lost. "
                                   "Set the stylus position by hand with G92 first.")
        self.send(self.gcode.setup())

    def position(self) -> tuple[float, float, float]:
        """Current X, Y, Z from M114."""
        self._serial.write(b"M114\n")
        pos = None
        while True:
            reply = self._serial.readline().decode(errors="replace").strip()
            if not reply:
                raise TimeoutError("No reply from machine for: M114")
            if reply.startswith("X:"):
                parts = dict(p.split(":") for p in reply.split()[:3])
                pos = (float(parts["X"]), float(parts["Y"]), float(parts["Z"]))
            elif reply.startswith("ok") and pos:
                return pos

    def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None

    def send(self, lines: list[str]) -> None:
        for line in lines:
            self.log.append(line)
            if self.cfg.dry_run:
                print(f"[dry-run] {line}")
            else:
                self._send_line(line)

    def _send_line(self, line: str) -> None:
        # Send one line and wait for the firmware's "ok"
        self._serial.write((line + "\n").encode())
        while True:
            reply = self._serial.readline().decode(errors="replace").strip()
            if not reply:
                raise TimeoutError(f"No reply from machine for: {line}")
            if reply.startswith("ok"):
                return
            if reply.lower().startswith("error"):
                raise RuntimeError(f"Machine error for '{line}': {reply}")

    # Phone actions (machine mm). M400 makes Marlin reply "ok" only after
    # the moves finish, so the next screenshot sees the result.

    def tap(self, x: float, y: float) -> None:
        self.send([*self.gcode.tap(x, y), "M400"])

    def long_press(self, x: float, y: float, ms: int = 800) -> None:
        self.send([*self.gcode.long_press(x, y, ms), "M400"])

    def double_tap(self, x: float, y: float) -> None:
        self.send([*self.gcode.double_tap(x, y), "M400"])

    def swipe(self, x1: float, y1: float, x2: float, y2: float, speed: float | None = None) -> None:
        self.send([*self.gcode.swipe(x1, y1, x2, y2, speed), "M400"])

    # Press / drag / release, for long presses and hand-made drags

    def press(self, x: float, y: float) -> None:
        self.send([*self.gcode.pen_up(), *self.gcode.move(x, y), *self.gcode.pen_down(), "M400"])

    def drag_to(self, x: float, y: float) -> None:
        self.send([*self.gcode.drag(x, y), "M400"])

    def release(self) -> None:
        self.send([*self.gcode.pen_up(), "M400"])
