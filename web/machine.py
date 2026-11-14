"""Machine buttons on the control page: Home and Calibrate. One job at a time, on the web server's
own serial connection (so the board is not reset in between). A finished calibration waits for the
user's answer (OK / Not OK) before it is saved and used."""

import threading
from pathlib import Path
from typing import Callable

from actuator import GcodeActuator
from calib import Calibration
from calib.run import CalibConfig, box_center, calibrate, check_summary
from PIL import Image
from robot import Machine


class MachineControl:
    def __init__(self, machine: Machine, actuator: GcodeActuator, cfg: CalibConfig,
                 grab: Callable[[], Image.Image], touches: Callable[[], list], calib_url: str = "",
                 show: Callable[[dict], None] = lambda view: None,
                 page: Callable[[], dict | None] = lambda: None):
        self.machine = machine
        self.actuator = actuator
        self.cfg = cfg
        self.grab = grab          # fresh phone image
        self.touches = touches    # touches the calibration page has seen
        self.show = show          # tells the calibration page what to draw
        self.page = page          # the calibration page's viewport, None if it is not open
        self.log: list[str] = []  # every line of the last calibration (each tap and its result)
        self.pending: Calibration | None = None  # a finished calibration the user has not answered yet
        self.calib_url = calib_url
        self.job: str | None = None  # "home" | "calibrate" while one runs
        self.message = ""
        self.stop = threading.Event()
        self._lock = threading.Lock()

    def state(self) -> dict:
        c = self.actuator.calib
        shown = self.pending or c
        return {
            "pending": self.pending is not None,
            "check": shown.check if shown else None,
            "log": self.log,
            "name": self.machine.cfg.name,
            "homed": self.machine.homed,
            "calibrated": c is not None,
            "error_mm": c.error_mm if c else None,
            "screen_box": c.screen_box if c else None,
            "job": self.job,
            "message": self.message,
            "calib_url": self.calib_url,
        }

    def start(self, job: str) -> None:
        """Runs "home" or "calibrate" in the background. Raises RuntimeError if it cannot start."""
        with self._lock:
            if self.job:
                raise RuntimeError(f"The machine is busy ({self.job})")
            self.job = job
            if job == "calibrate":
                self.pending = None
        self.stop.clear()
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"machine-{job}").start()

    def _run(self, job: str) -> None:
        try:
            if job == "home":
                self.message = "Homing X/Y..."
                self.machine.home()
                self.message = "Homed"
            else:
                self._calibrate()
        except Exception as err:  # serial error, no mirror, calibration failed
            self.message = f"{job} failed: {err}"
        finally:
            self.job = None

    def _calibrate(self) -> None:
        self.log = []

        def say(text: str) -> None:
            self.message = text
            self.log.append(text)
            print(f"calib: {text}", flush=True)

        say("Homing X/Y before calibrating...")
        self.machine.home()  # the map is only as good as the position it is made from
        last = self.actuator.calib
        cfg = self.machine.cfg
        result = calibrate(self.machine.tap, self.grab, self.touches, cfg.x_max, cfg.y_max, self.cfg,
                           seed=box_center(last.screen_box) if last else None, say=say, stop=self.stop.is_set,
                           show=self.show, page=self.page)
        self.pending = result
        self.message = (f"{check_summary(result.check)}. Fit error {result.error_mm:.2f} mm, "
                        f"screen box {result.screen_box} mm. Is it OK?")

    def answer(self, ok: bool) -> None:
        """The user's answer to "Is it OK?": save and use the new calibration, or throw it away."""
        with self._lock:
            result, self.pending = self.pending, None
        if result is None:
            raise RuntimeError("No calibration is waiting for an answer")
        if ok:
            Path(self.cfg.file).parent.mkdir(exist_ok=True)
            result.save(self.cfg.file)
            self.actuator.calib = result
            self.message = f"Calibration saved: fit error {result.error_mm:.2f} mm, screen box {result.screen_box} mm"
        else:
            self.message = "Calibration not saved"
        self.show({"round": -1, "title": self.message, "targets": []})
