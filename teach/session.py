"""The teaching side of the web server: one open recording, the human actuator, skill drafts."""

import difflib
import io
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from actuator.human import HumanActuator
from contract import Gesture
from teach.recorder import Recorder
from teach.skill_writer import fix_skill, render_screen, tidy, write_skill
from teach.store import TeachConfig, find_recording, list_apps, list_recordings, load_recording, slug
from teach.validate import validate_skill
from vision.feed import FrameFeed


class TeachError(Exception):
    def __init__(self, status: int, code: str, detail: str = "", extra: dict | None = None):
        super().__init__(detail or code)
        self.status, self.code, self.detail, self.extra = status, code, detail or code, extra or {}


@dataclass
class Draft:
    draft_id: str
    app_id: str
    rec_id: str
    status: str = "writing"          # writing | ready | error | approved
    error: str | None = None
    skill_md: str = ""
    current_md: str = ""
    screens: list[dict] = field(default_factory=list)   # new: {name, seq, box, marks, rec_id}; kept: {name, existing}
    sources: list[str] = field(default_factory=list)
    inferred: list[dict] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)  # screen images already in the skill folder
    note: str | None = None                            # e.g. "Claude fixed 2 problems"

    def diff(self) -> str:
        return "".join(difflib.unified_diff(
            self.current_md.splitlines(True), self.skill_md.splitlines(True),
            "SKILL.md (current)", "SKILL.md (draft)"))


class TeachController:
    def __init__(self, feed: FrameFeed, human: HumanActuator, cfg: TeachConfig,
                 client_factory: Callable[[], object], agent_running: Callable[[], bool] = lambda: False):
        self.feed = feed
        self.human = human
        self.cfg = cfg
        self.client_factory = client_factory
        self.agent_running = agent_running
        self.rec_root = Path(cfg.recordings_dir)
        self.skills_root = Path(cfg.skills_dir)
        self.rec: Recorder | None = None
        self.drafts: dict[str, Draft] = {}
        self._act_lock = threading.Lock()

    # Session

    def start(self, goal: str, app_name: str = "", app_id: str = "", bundle_id: str | None = None,
              mode: str = "watch") -> str:
        if self.rec and not self.rec.closed:
            raise TeachError(409, "session_open", "A teaching session is already open")
        if self.agent_running():
            raise TeachError(409, "busy", "The agent is running a task; stop it first")
        if mode != "watch":
            raise TeachError(400, "unsupported", "Only Watch mode: you do each move on the device yourself")
        if not goal.strip():
            raise TeachError(400, "bad_request", "Type the task goal")
        app_name = app_name.strip()
        if not app_name and not app_id.strip():
            raise TeachError(400, "bad_request", "Type the app name")
        app_id = slug(app_id or app_name)
        frame = self.feed.latest()
        if frame is None:
            raise TeachError(409, "screen_unavailable", "No picture of the device yet; start screen mirroring")
        w, h = frame.size
        rec = Recorder(
            self.rec_root,
            app={"app_id": app_id, "name": app_name or app_id, "bundle_id": bundle_id, "version": None},
            goal=goal.strip(),
            mode=mode,
            feed=self.feed,
            device={"profile": self.cfg.device_profile, "os": self.cfg.os, "aspect": round(w / h, 4),
                    "orientation": "portrait" if h >= w else "landscape"},
            backend={"client": "local", "screen_source": "mac-window", "actuator": "human"},
            quiet=self.cfg.settle_quiet_s,
            most=self.cfg.settle_most_s,
            change_threshold=self.cfg.change_threshold,
        )
        rec.start()
        self.rec = rec
        self.human.stop_event.clear()
        self.human.timeout = self.cfg.prompt_timeout_s
        return rec.id

    def _open(self, session_id: str | None = None) -> Recorder:
        if not self.rec or self.rec.closed:
            raise TeachError(409, "no_session", "No teaching session is open")
        if session_id and session_id != self.rec.id:
            raise TeachError(404, "not_found", "Not the open session")
        return self.rec

    def act(self, session_id: str, gesture_json: dict) -> dict:
        rec = self._open(session_id)
        try:
            gesture = Gesture.from_dict(gesture_json)
        except (KeyError, TypeError, ValueError) as err:
            raise TeachError(400, "bad_gesture", str(err))
        if rec.paused:
            rec.dropped(f"{gesture.type} while stopped")
            raise TeachError(409, "stopped", "Recording is stopped; press Resume first")
        if not self._act_lock.acquire(blocking=False):
            rec.dropped(f"{gesture.type} while a move was open")
            raise TeachError(409, "busy", "A move is still open; finish it first")
        try:
            step = rec.begin_gesture()
            result = self.human.execute(gesture)
            rec.end_gesture(step, gesture, "human", result)
            return {"step": step, "ok": result.ok, "error": result.error}
        finally:
            self._act_lock.release()

    def drop(self, session_id: str, what: str) -> None:
        self._open(session_id).dropped(what)

    def note(self, session_id: str, text: str, step: int | None = None) -> int:
        if not text.strip():
            raise TeachError(400, "bad_request", "Empty note")
        return self._open(session_id).note(text.strip(), step)

    def mark(self, session_id: str, box: list[float], label: str, step: int | None = None) -> int:
        if len(box) != 4 or not label.strip():
            raise TeachError(400, "bad_request", "A mark needs a box [x0, y0, x1, y1] and a label")
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in box)
        return self._open(session_id).mark([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], label.strip(), step)

    def stop(self, session_id: str) -> None:
        rec = self._open(session_id)
        self.human.stop()
        rec.pause()

    def resume(self, session_id: str) -> None:
        self._open(session_id).resume()

    def finish(self, session_id: str, outcome: str, note: str | None = None) -> str:
        if outcome not in ("success", "failed", "partial"):
            raise TeachError(400, "bad_request", "outcome must be success, failed or partial")
        rec = self._open(session_id)
        self.human.stop()
        return str(rec.finish(outcome, (note or "").strip() or None))

    def state(self) -> dict:
        rec = self.rec
        if not rec:
            return {"session": None}
        return {"session": {
            "session_id": rec.id,
            "app": rec.session["app"],
            "goal": rec.session["goal"],
            "open": not rec.closed,
            "paused": rec.paused,
            "busy": rec.busy,
            "step": rec.step,
            "outcome": rec.session["outcome"],
            "events": [e for e in rec.events if e["type"] != "frame"][-60:],
        }}

    # Apps and recordings

    def apps(self) -> list[dict]:
        return list_apps(self.rec_root, self.skills_root)

    def recordings(self, app_id: str) -> list[dict]:
        return list_recordings(self.rec_root, app_id)

    def recording(self, rec_id: str) -> dict:
        path = find_recording(self.rec_root, rec_id)
        if not path:
            raise TeachError(404, "not_found", "No such recording")
        session, events = load_recording(path)
        return {"session": session, "events": events}

    def frame_path(self, rec_id: str, seq: int) -> Path:
        path = find_recording(self.rec_root, rec_id)
        f = path / "frames" / f"{int(seq)}.jpg" if path else None
        if not f or not f.exists():
            raise TeachError(404, "not_found", "No such frame")
        return f

    # Skill drafts

    def _skill_dir(self, app_id: str) -> Path:
        return self.skills_root / app_id

    def start_draft(self, rec_id: str) -> str:
        path = find_recording(self.rec_root, rec_id)
        if not path:
            raise TeachError(404, "not_found", "No such recording")
        session, _ = load_recording(path)
        if not session.get("finished"):
            raise TeachError(409, "not_finished", "Finish the recording first")
        app_id = session["app"]["app_id"]
        skill_dir = self._skill_dir(app_id)
        current = (skill_dir / "SKILL.md").read_text() if (skill_dir / "SKILL.md").exists() else ""
        old_sources = []
        if (skill_dir / "sources.json").exists():
            old_sources = json.loads((skill_dir / "sources.json").read_text()).get("recordings", [])
        draft = Draft(secrets.token_hex(4), app_id, rec_id, current_md=current,
                      sources=sorted(set(old_sources) | {rec_id}))
        self.drafts[draft.draft_id] = draft
        existing = sorted(p.stem for p in (skill_dir / "screens").glob("*.jpg"))
        threading.Thread(target=self._write, args=(draft, path, existing), daemon=True).start()
        return draft.draft_id

    def _write(self, draft: Draft, rec_path: Path, existing: list[str]) -> None:
        draft.existing = existing
        try:
            result = write_skill(self.client_factory(), self.cfg.skill_writer, rec_path, draft.current_md or None,
                                 existing)
            self._set(draft, result.skill_md, result.screens)
            draft.inferred = result.inferred
            # One automatic correction pass if the checker still finds errors
            errors = [p for p in self.problems(draft, force=True) if p["level"] == "error"]
            if errors:
                self._fix(draft, errors)
                left = [p for p in self.problems(draft, force=True) if p["level"] == "error"]
                draft.note = f"Claude fixed {len(errors) - len(left)} of {len(errors)} problem(s) automatically."
            draft.status = "ready"
        except Exception as err:  # API error, bad JSON
            draft.status, draft.error = "error", f"{type(err).__name__}: {err}"

    def _set(self, draft: Draft, skill_md: str, screens: list[dict]) -> None:
        skill_md, screens = tidy(draft.app_id, skill_md, screens)
        names = {s["name"] for s in screens}
        draft.skill_md = skill_md
        draft.screens = screens + [{"name": n, "existing": True} for n in draft.existing if n not in names]

    def _fix(self, draft: Draft, problems: list[dict]) -> None:
        r = fix_skill(self.client_factory(), self.cfg.skill_writer, draft.app_id, draft.skill_md, draft.screens,
                      draft.existing, problems)
        self._set(draft, r.skill_md, r.screens)

    def fix_draft(self, draft_id: str) -> None:
        """The page's 'Ask Claude to fix' button: one correction pass on the current text."""
        d = self._draft(draft_id)
        if d.status != "ready":
            raise TeachError(409, "not_ready", f"Draft is {d.status}")
        problems = self.problems(d)
        if not problems:
            raise TeachError(409, "nothing_to_fix", "No problems to fix")
        d.status, d.note = "writing", None

        def run():
            try:
                self._fix(d, problems)
                left = [p for p in self.problems(d, force=True) if p["level"] == "error"]
                d.note = "Claude fixed the problems." if not left else f"{len(left)} error(s) are still left."
                d.status = "ready"
            except Exception as err:
                d.status, d.note = "ready", f"Fixing failed: {type(err).__name__}: {err}"

        threading.Thread(target=run, daemon=True).start()

    def _draft(self, draft_id: str) -> Draft:
        d = self.drafts.get(draft_id)
        if not d:
            raise TeachError(404, "not_found", "No such draft")
        return d

    def problems(self, d: Draft, force: bool = False) -> list[dict]:
        if not force and d.status not in ("ready", "approved"):
            return []
        return [p.to_dict() for p in validate_skill(d.app_id, d.skill_md, d.screens, d.sources, self.rec_root)]

    def draft(self, draft_id: str) -> dict:
        d = self._draft(draft_id)
        return {"draft_id": d.draft_id, "app_id": d.app_id, "rec_id": d.rec_id, "status": d.status,
                "error": d.error, "skill_md": d.skill_md, "screens": d.screens, "sources": d.sources,
                "inferred": d.inferred, "note": d.note, "diff": d.diff() if d.status != "writing" else "",
                "problems": self.problems(d)}

    def update_draft(self, draft_id: str, skill_md: str, screens: list[dict] | None = None) -> None:
        d = self._draft(draft_id)
        if d.status != "ready":
            raise TeachError(409, "not_ready", f"Draft is {d.status}")
        d.skill_md, d.note = skill_md, None
        if screens is not None:
            known = {s["name"]: s for s in d.screens}
            d.screens = [known.get(s.get("name"), s) if s.get("existing") else s for s in screens]

    def screen_jpeg(self, draft_id: str, name: str) -> bytes:
        d = self._draft(draft_id)
        s = next((s for s in d.screens if s["name"] == name), None)
        if not s:
            raise TeachError(404, "not_found", "No such screen")
        if s.get("existing"):
            return (self._skill_dir(d.app_id) / "screens" / f"{name}.jpg").read_bytes()
        buf = io.BytesIO()
        render_screen(self.rec_root, s).save(buf, "JPEG", quality=85)
        return buf.getvalue()

    def approve(self, draft_id: str) -> str:
        d = self._draft(draft_id)
        if d.status != "ready":
            raise TeachError(409, "not_ready", f"Draft is {d.status}")
        problems = self.problems(d)
        if any(p["level"] == "error" for p in problems):
            raise TeachError(409, "invalid_skill", "Fix the errors first", {"problems": problems})
        skill_dir = self._skill_dir(d.app_id)
        (skill_dir / "screens").mkdir(parents=True, exist_ok=True)
        for s in d.screens:
            if not s.get("existing") and f"](screens/{s['name']}.jpg)" in d.skill_md:
                render_screen(self.rec_root, s).save(skill_dir / "screens" / f"{s['name']}.jpg", "JPEG", quality=85)
        (skill_dir / "SKILL.md").write_text(d.skill_md)
        (skill_dir / "sources.json").write_text(json.dumps(
            {"recordings": d.sources, "updated": time.strftime("%Y-%m-%d")}, indent=2))
        d.status = "approved"
        return str(skill_dir / "SKILL.md")
