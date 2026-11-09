"""The `human` actuator: a person is the hardware (docs/human-actuator-teaching-ui.md 4.7).

execute(gesture) opens a prompt ("Tap here", drawn on the live image) and returns when the person has done
it on the device and answered Done / Skip / Failed. The web page shows the open prompt and sends the answer.
The agent's pixel methods (tap, swipe, ...) are thin wrappers that convert phone pixels to screen fractions.
"""

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from contract import ActResult, Capabilities, Gesture, Health, Limits

ANSWERS = ("done", "skipped", "failed")


@dataclass(frozen=True)
class HumanPrompt:
    prompt_id: str
    gesture: Gesture
    say: str
    deadline: float | None  # time.time() after which it times out; None = no timeout

    def to_dict(self) -> dict:
        return {"prompt_id": self.prompt_id, "gesture": self.gesture.to_dict(), "say": self.say,
                "deadline": self.deadline}


def say_for(g: Gesture) -> str:
    t = g.type
    if t == "tap":
        return "Tap here"
    if t == "double_tap":
        return "Double-tap here"
    if t == "long_press":
        return f"Long-press here for {g.limits.hold or 0.8:.1f} s"
    if t == "swipe":
        return "Swipe along the arrow"
    if t == "drag":
        return "Drag along the arrow and hold at the end" if g.limits.hold_end else "Drag along the arrow"
    if t == "scroll":
        return f"Scroll {'up' if g.lines > 0 else 'down'} {abs(g.lines) or 1} lines here"
    if t == "type":
        return f"Type: {g.text}"
    if t == "key":
        return f"Press {g.key}"
    if t == "home":
        return "Go to the Home Screen"
    if t == "back":
        return "Go back (swipe right from the left edge)"
    if t == "touch_down":
        return "Press here and keep holding"
    if t == "touch_move":
        return "Keep holding and move here"
    if t in ("touch_up", "release_all"):
        return "Lift your finger"
    return t


class HumanActuator:
    capabilities = Capabilities(
        pointer="absolute",
        gestures=frozenset({"tap", "double_tap", "long_press", "swipe", "drag", "scroll", "type", "key",
                            "home", "back", "release_all", "touch_down", "touch_move", "touch_up"}),
        keys=frozenset({"home", "enter", "tab", "esc", "backspace", "cmd+<letter>"}),
        text=True,
        needs_observer=False,
        typical_error=0.01,
    )

    def __init__(
        self,
        screen_size: Callable[[], tuple[int, int]] | None = None,
        on_prompt: Callable[[HumanPrompt | None], None] | None = None,
        stop: threading.Event | None = None,
        timeout: float | None = None,
    ):
        """screen_size: phone pixel size, for the agent's pixel methods.
        on_prompt: called with each prompt and None when it closes; set it when no web page shows prompts
        (e.g. the terminal), and answer from inside it.
        stop: an outside stop flag (the agent session's Stop button); cancels the open prompt.
        timeout: seconds before an unanswered prompt times out; None = wait forever."""
        self.screen_size = screen_size
        self.on_prompt = on_prompt
        self.stop_event = stop or threading.Event()
        self.timeout = timeout
        self.prompt: HumanPrompt | None = None
        self._answer: tuple[str, str | None] | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._last_seen = 0.0

    # The web page

    def seen(self) -> None:
        """A page is showing prompts (called on every page poll)."""
        self._last_seen = time.monotonic()

    def listening(self) -> bool:
        return self.on_prompt is not None or time.monotonic() - self._last_seen < 5.0

    def answer(self, prompt_id: str, result: str = "done", note: str | None = None) -> bool:
        """The person's answer to the open prompt. False if it is not open (already answered or gone)."""
        if result not in ANSWERS:
            raise ValueError(f"result must be one of {ANSWERS}")
        with self._lock:
            if not self.prompt or self.prompt.prompt_id != prompt_id or self._answer:
                return False
            self._answer = (result, note)
        self._wake.set()
        return True

    def done(self) -> bool:
        """Done for whatever prompt is open (the agent page's Done button / Space)."""
        p = self.prompt
        return bool(p) and self.answer(p.prompt_id, "done")

    # Actuator interface

    def execute(self, gesture: Gesture) -> ActResult:
        started = time.time()
        if gesture.type not in self.capabilities.gestures:
            return ActResult(False, "unsupported", started, time.time())
        if not self.listening():
            return ActResult(False, "device_unavailable", started, time.time())
        with self._lock:
            if self.prompt:
                return ActResult(False, "busy", started, time.time())
            deadline = started + self.timeout if self.timeout else None
            self.prompt = HumanPrompt(uuid.uuid4().hex[:8], gesture, say_for(gesture), deadline)
            self._answer = None
            self._wake.clear()
        try:
            if self.on_prompt:
                self.on_prompt(self.prompt)
            while True:
                if self._answer:
                    result, note = self._answer
                    ok = result == "done"
                    return ActResult(ok, None if ok else result, started, time.time(), note)
                if self.stop_event.is_set():
                    return ActResult(False, "stopped", started, time.time())
                if deadline and time.time() > deadline:
                    return ActResult(False, "timeout", started, time.time())
                self._wake.wait(0.2)
        finally:
            with self._lock:
                self.prompt = None
            if self.on_prompt:
                self.on_prompt(None)

    def home(self) -> ActResult:
        return self.execute(Gesture("home"))

    def stop(self) -> None:
        """Cancel the open prompt (its result is 'stopped')."""
        p = self.prompt
        if p:
            with self._lock:
                if self.prompt is p and not self._answer:
                    self._answer = ("stopped", None)
            self._wake.set()

    def calibrate(self) -> bool:
        return True

    def calibrated(self) -> bool:
        return True

    def health(self) -> Health:
        if not self.listening():
            return Health("down", "no page open to show moves")
        return Health("ok")

    # The agent's pixel methods (phone pixels in). Raise on anything but Done, like the machine would on error.

    def tap(self, x: float, y: float) -> None:
        self._run(Gesture("tap", (self._norm(x, y),)))

    def double_tap(self, x: float, y: float) -> None:
        self._run(Gesture("double_tap", (self._norm(x, y),)))

    def swipe(self, x1: float, y1: float, x2: float, y2: float, fast: bool = False) -> None:
        self._run(Gesture("swipe", (self._norm(x1, y1), self._norm(x2, y2)), limits=Limits(hold_end=not fast)))

    def press(self, x: float, y: float) -> None:
        self._run(Gesture("touch_down", (self._norm(x, y),)))

    def drag_to(self, x: float, y: float) -> None:
        self._run(Gesture("touch_move", (self._norm(x, y),)))

    def release(self) -> None:
        self._run(Gesture("touch_up"))

    def _norm(self, x: float, y: float) -> tuple[float, float]:
        if not self.screen_size:
            raise RuntimeError("HumanActuator needs screen_size for pixel coordinates")
        w, h = self.screen_size()
        return min(max(x / w, 0.0), 1.0), min(max(y / h, 0.0), 1.0)

    def _run(self, g: Gesture) -> None:
        r = self.execute(g)
        if r.error == "stopped":
            raise RuntimeError("Stopped by the user")
        if not r.ok:
            raise RuntimeError(f"Move not done: {r.error}" + (f" ({r.note})" if r.note else ""))
