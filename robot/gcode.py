"""Builds G-code for phone actions. Coordinates are machine mm."""

from robot.config import RobotConfig


class GcodeBuilder:
    def __init__(self, cfg: RobotConfig):
        self.cfg = cfg

    def setup(self) -> list[str]:
        lines = ["G21", "G90"]  # mm, absolute positioning
        if self.cfg.z_at_connect is not None:
            lines.append(f"G92 Z{self.cfg.z_at_connect:.2f}")
        if self.cfg.z_accel:
            lines.append(f"M201 Z{self.cfg.z_accel:.0f}")
        lines += self.pen_up()  # lift before homing so the stylus doesn't drag on the glass
        if self.cfg.home_on_start:
            lines.append("G28 X0 Y0")  # never home Z: it drives the bed into the stylus
        return lines

    def pen_up(self) -> list[str]:
        return [f"G1 Z{self.cfg.z_up:.2f} F{self.cfg.z_speed:.0f}"]

    def pen_down(self) -> list[str]:
        return [f"G1 Z{self.cfg.z_touch:.2f} F{self.cfg.z_speed:.0f}"]

    def move(self, x: float, y: float) -> list[str]:
        self._check(x, y)
        return [f"G0 X{x:.2f} Y{y:.2f} F{self.cfg.move_speed:.0f}"]

    def dwell(self, ms: int) -> list[str]:
        if self.cfg.dwell_in_seconds:
            return [f"G4 P{ms / 1000:.3f}"]
        return [f"G4 P{ms}"]

    def tap(self, x: float, y: float) -> list[str]:
        return [*self.pen_up(), *self.move(x, y), *self.pen_down(),
                *self.dwell(self.cfg.tap_hold_ms), *self.pen_up()]

    def long_press(self, x: float, y: float, ms: int = 800) -> list[str]:
        return [*self.pen_up(), *self.move(x, y), *self.pen_down(),
                *self.dwell(ms), *self.pen_up()]

    def double_tap(self, x: float, y: float) -> list[str]:
        # Small lift between the taps so both land within iOS's double-tap time
        lift = [f"G1 Z{self.cfg.z_touch + self.cfg.double_tap_lift:.2f} F{self.cfg.z_speed:.0f}"]
        hold = self.dwell(self.cfg.tap_hold_ms)
        return [*self.pen_up(), *self.move(x, y), *self.pen_down(), *hold,
                *lift, *self.pen_down(), *hold, *self.pen_up()]

    def drag(self, x: float, y: float, speed: float | None = None) -> list[str]:
        """Move in X/Y at the current Z (stylus down = drag on the screen)."""
        self._check(x, y)
        return [f"G1 X{x:.2f} Y{y:.2f} F{speed or self.cfg.swipe_speed:.0f}"]

    def swipe(self, x1: float, y1: float, x2: float, y2: float, speed: float | None = None) -> list[str]:
        return [*self.pen_up(), *self.move(x1, y1), *self.pen_down(),
                *self.drag(x2, y2, speed), *self.pen_up()]

    def _check(self, x: float, y: float) -> None:
        if not (0 <= x <= self.cfg.x_max and 0 <= y <= self.cfg.y_max):
            raise ValueError(
                f"Point ({x:.2f}, {y:.2f}) is outside the work area "
                f"(0..{self.cfg.x_max}, 0..{self.cfg.y_max})"
            )
