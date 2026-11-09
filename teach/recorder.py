"""Records one teaching session to disk (docs/human-actuator-teaching-ui.md 4.4).

recordings/<app_id>/<YYYYMMDD-HHMMSS>-<short id>/
  session.json   who, what, which device
  events.jsonl   one event per line, in time order
  frames/<seq>.jpg

A step is one gesture (entered on the image, done by the person) or one settled screen change with no gesture
running (a free touch on the device: an inferred step), with its before and after frame.
"""

import json
import secrets
import threading
import time
from pathlib import Path

from contract import ActResult, Gesture
from vision.feed import FeedFrame, FrameFeed, screen_diff

SCHEMA = 1


class Recorder:
    def __init__(
        self,
        root: Path,
        app: dict,
        goal: str,
        mode: str,
        feed: FrameFeed,
        device: dict,
        backend: dict,
        quiet: float = 0.6,
        most: float = 4.0,
        change_threshold: float = 2.0,
    ):
        now = time.localtime()
        self.id = time.strftime("%Y%m%d-%H%M%S", now) + "-" + secrets.token_hex(2)
        self.path = Path(root) / app["app_id"] / self.id
        self.feed = feed
        self.quiet, self.most, self.threshold = quiet, most, change_threshold
        self.step = 0                        # latest step number; notes and marks attach to it
        self.events: list[dict] = []
        self.paused = False
        self.closed = False
        self.busy = False                    # a gesture is running (the inferred-step watcher waits)
        self._base: FeedFrame | None = None  # last settled frame, the "before" of the next step
        self._saved: set[int] = set()
        self._pending_before: int | None = None
        self._lock = threading.RLock()
        self.session = {
            "session_id": self.id,
            "app": app,
            "goal": goal,
            "mode": mode,
            "device": device,
            "backend": backend,
            "started": time.time(),
            "finished": None,
            "outcome": None,
            "outcome_note": None,
            "schema": SCHEMA,
        }
        self._watcher: threading.Thread | None = None

    # Lifecycle

    def start(self) -> None:
        (self.path / "frames").mkdir(parents=True, exist_ok=False)
        self._base = self.feed.latest()
        self._write_session()
        self._watcher = threading.Thread(target=self._watch, daemon=True, name="teach-watch")
        self._watcher.start()

    def finish(self, outcome: str, note: str | None = None) -> Path:
        with self._lock:
            if self.closed:
                return self.path
            self.closed = True
            self._event("outcome", outcome=outcome, note=note)
            self.session.update(finished=time.time(), outcome=outcome, outcome_note=note)
            self._write_session()
        return self.path

    def pause(self) -> None:
        with self._lock:
            self.paused = True
            self._event("control", action="stop")

    def resume(self) -> None:
        with self._lock:
            self.paused = False
            self._base = self.feed.latest()  # changes made while paused are not recorded
            self._event("control", action="resume")

    def dropped(self, what: str) -> None:
        with self._lock:
            self._event("control", action="drop", detail=what)

    # Gestures

    def begin_gesture(self) -> int:
        """Marks the gesture as running and saves the 'before' frame. Returns the step number it will get."""
        with self._lock:
            self.busy = True
            step = self.step + 1
            before = self.feed.latest()
            if before:
                self._frame(before, step, "before")
            self._pending_before = before.seq if before else None
            return step

    def end_gesture(self, step: int, gesture: Gesture, actor: str, result: ActResult) -> None:
        """Waits for the screen to settle, saves the 'after' frame and the gesture event."""
        try:
            after = self.feed.settled(self.quiet, self.most)
            with self._lock:
                if after:
                    self._frame(after, step, "after")
                    self._base = after
                self.step = step
                self._event("gesture", step=step, gesture=gesture.to_dict(), actor=actor, ok=result.ok,
                            error=result.error, note=result.note, before_seq=self._pending_before,
                            after_seq=after.seq if after else None)
        finally:
            self.busy = False

    # Notes and marks

    def note(self, text: str, step: int | None = None) -> int:
        with self._lock:
            step = self.step if step is None else step
            self._event("note", step=step, text=text)
            return step

    def mark(self, box: list[float], label: str, step: int | None = None) -> int:
        with self._lock:
            step = self.step if step is None else step
            frame = self.feed.latest()
            seq = None
            if frame:
                self._save_jpeg(frame)
                seq = frame.seq
            self._event("mark", step=step, box=[round(v, 4) for v in box], label=label, seq=seq)
            return step

    # Inferred steps: the screen changed and settled while no gesture was running

    def _watch(self) -> None:
        while not self.closed:
            time.sleep(0.2)
            if self.busy or self.paused or self.closed:
                continue
            cur = self.feed.latest()
            if cur is None:
                continue
            if self._base is None:
                self._base = cur
                continue
            if cur.seq == self._base.seq or screen_diff(self._base.image, cur.image) <= self.threshold:
                continue
            after = self.feed.settled(self.quiet, self.most)
            with self._lock:
                if self.busy or self.paused or self.closed or after is None:
                    continue  # a gesture started meanwhile; it records its own before/after
                before = self._base
                step = self.step + 1
                self._frame(before, step, "before")
                self._frame(after, step, "after")
                self.step = step
                self._event("step", step=step, before_seq=before.seq, after_seq=after.seq, inferred=True)
                self._base = after

    # Files

    def _frame(self, f: FeedFrame, step: int, role: str) -> None:
        self._save_jpeg(f)
        self._event("frame", step=step, seq=f.seq, path=f"frames/{f.seq}.jpg", width=f.size[0],
                    height=f.size[1], role=role)

    def _save_jpeg(self, f: FeedFrame) -> None:
        if f.seq not in self._saved:
            (self.path / "frames" / f"{f.seq}.jpg").write_bytes(f.jpeg)
            self._saved.add(f.seq)

    def _event(self, type_: str, step: int | None = None, **fields) -> None:
        ev = {"type": type_, "t": time.time(), "step": self.step if step is None else step, **fields}
        self.events.append(ev)
        with open(self.path / "events.jsonl", "a") as fh:
            fh.write(json.dumps(ev) + "\n")

    def _write_session(self) -> None:
        (self.path / "session.json").write_text(json.dumps(self.session, indent=2))
