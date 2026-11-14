"""Builds G-code for phone actions. Coordinates are machine mm."""

from robot.config import RobotConfig


class GcodeBuilder:
    def __init__(self, cfg: RobotConfig):
        if cfg.z_mode not in ("height", "cam"):
            raise ValueError(f"z_mode must be 'height' or 'cam', not '{cfg.z_mode}'")
        self.cfg = cfg
        self.cam = cfg.z_mode == "cam"
        # Cam mode: every pen_up/pen_down turns the cam, so the builder tracks where the stylus is
        # (a pen_up while already up would turn a full circle and tap the glass).
        self.pen_is_down = False

    def setup(self) -> list[str]:
        lines = ["G21", "G90"]  # mm, absolute positioning
        if self.cam:
            # The stylus must be up when connecting; cam Z counts from 0 = up
            lines.append("G92 Z0")
            self.pen_is_down = False
        elif self.cfg.z_at_connect is not None:
            lines.append(f"G92 Z{self.cfg.z_at_connect:.2f}")
        if self.cfg.y_steps_per_mm:
            lines.append(f"M92 Y{self.cfg.y_steps_per_mm:g}")
        if self.cfg.z_max_speed:
            lines.append(f"M203 Z{self.cfg.z_max_speed:.0f}")
        if self.cfg.z_accel:
            lines.append(f"M201 Z{self.cfg.z_accel:.0f}")
        lines += self.pen_up()  # lift before homing so the stylus doesn't drag on the glass
        if self.cfg.home_on_start and not self.cfg.home_by_order:
            lines += self.home()
        return lines

    def home(self) -> list[str]:
        # Never home Z (no Z switch). R0 = Marlin must not raise Z before homing X/Y:
        # on a cam that raise would turn the cam and press the stylus down.
        return [*self.pen_up(), "G28 X Y R0"]

    def pen_up(self) -> list[str]:
        if self.cam:
            if not self.pen_is_down:
                return []
            self.pen_is_down = False
            # Second half turn forward = up; then count Z from 0 again so it never reaches the soft limit
            return [f"G1 Z{2 * self.cfg.cam_half_turn:.2f} F{self.cfg.z_speed:.0f}", "G92 Z0"]
        return [f"G1 Z{self.cfg.z_up:.2f} F{self.cfg.z_speed:.0f}"]

    def pen_down(self) -> list[str]:
        if self.cam:
            if self.pen_is_down:
                return []
            self.pen_is_down = True
            return [f"G1 Z{self.cfg.cam_half_turn:.2f} F{self.cfg.z_speed:.0f}"]
        return [f"G1 Z{self.cfg.z_touch:.2f} F{self.cfg.z_speed:.0f}"]

    def move(self, x: float, y: float) -> list[str]:
        self._check(x, y)
        return [f"G0 X{x:.2f} Y{y:.2f} F{self.cfg.move_speed:.0f}"]

    def dwell(self, ms: int) -> list[str]:
        if ms <= 0:
            return []
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
        hold = self.dwell(self.cfg.tap_hold_ms)
        lines = [*self.pen_up(), *self.move(x, y), *self.pen_down(), *hold]
        if self.cam:
            lift = self.pen_up()  # the cam can only lift all the way: one full turn between the taps
        else:
            # Small lift between the taps so both land within iOS's double-tap time
            lift = [f"G1 Z{self.cfg.z_touch + self.cfg.double_tap_lift:.2f} F{self.cfg.z_speed:.0f}"]
        return [*lines, *lift, *self.pen_down(), *hold, *self.pen_up()]

    def drag(self, x: float, y: float, speed: float | None = None) -> list[str]:
        """Move in X/Y at the current Z (stylus down = drag on the screen)."""
        self._check(x, y)
        return [f"G1 X{x:.2f} Y{y:.2f} F{speed or self.cfg.swipe_speed:.0f}"]

    def swipe(self, x1: float, y1: float, x2: float, y2: float, speed: float | None = None) -> list[str]:
        self._check(x2, y2)  # before pen_down changes the cam state
        return [*self.pen_up(), *self.move(x1, y1), *self.pen_down(),
                *self.drag(x2, y2, speed), *self.pen_up()]

    def _check(self, x: float, y: float) -> None:
        if not (0 <= x <= self.cfg.x_max and 0 <= y <= self.cfg.y_max):
            raise ValueError(
                f"Point ({x:.2f}, {y:.2f}) is outside the work area "
                f"(0..{self.cfg.x_max}, 0..{self.cfg.y_max})"
            )
