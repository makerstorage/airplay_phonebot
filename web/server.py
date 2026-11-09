"""Control page: live phone screen, the agent (task / plan / steps / ask / stop) and teaching
(record a task done by hand, turn it into a skill)."""

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from actuator import HumanActuator
from agent import Agent
from teach import TeachController, TeachError
from vision.feed import FrameFeed

PAGE = (Path(__file__).parent / "page.html").read_text()
MAX_STEPS_SHOWN = 300


class Session:
    """Agent state shared by the agent thread and the web page."""

    def __init__(self, mode: str):
        self.mode = mode
        self.status = "idle"  # idle | running | done | stopped | error
        self.task = ""
        self.plan: list[dict] = []
        self.steps: list[dict] = []
        self.question: str | None = None
        self.stop = threading.Event()
        self._answers: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()

    # Called from the agent thread

    def ask(self, question: str) -> str:
        self.question = question
        try:
            while True:
                try:
                    return self._answers.get(timeout=0.2)
                except queue.Empty:
                    if self.stop.is_set():
                        raise RuntimeError("Stopped by the user")
        finally:
            self.question = None

    def on_event(self, kind: str, data: dict) -> None:
        if kind in ("screenshot", "usage"):
            return
        if kind == "plan":
            self.plan = data["items"]
            return
        if kind == "action":
            text = f"{data['name']} {data['input']}" if data["input"] else data["name"]
        else:
            text = str(next(iter(data.values()), ""))
        if kind in ("done", "stopped", "error") and self.status == "running":
            self.status = kind
        self._add_step(kind, text)

    # Called from the web page

    def answer(self, text: str) -> None:
        self._answers.put(text)

    def reset(self) -> None:
        # Clean slate for the next task; each task already gets a fresh Agent
        self.status, self.task, self.plan, self.steps = "idle", "", [], []
        self.question = None

    def state(self) -> dict:
        return {
            "mode": self.mode,
            "status": self.status,
            "task": self.task,
            "plan": self.plan,
            "steps": self.steps,
            "question": self.question,
        }

    def _add_step(self, kind: str, text: str) -> None:
        with self._lock:
            self.steps.append({"kind": kind, "text": text, "t": time.time()})
            del self.steps[:-MAX_STEPS_SHOWN]


def create_app(
    feed: FrameFeed,
    session: Session,
    new_agent: Callable[[], Agent],
    human: HumanActuator | None = None,
    teach: TeachController | None = None,
    fps: float = 5,
) -> FastAPI:
    """new_agent builds a fresh Agent per task. human shows moves for a person to do (the agent in human mode,
    and teaching). teach is the teaching controller (None = no Teach tab)."""
    app = FastAPI()

    @app.exception_handler(TeachError)
    def teach_error(_: Request, err: TeachError):
        return JSONResponse({"error": err.code, "detail": err.detail, **err.extra}, status_code=err.status)

    def need_teach() -> TeachController:
        if teach is None:
            raise TeachError(400, "unsupported", "Teaching is not set up")
        return teach

    @app.get("/")
    def index():
        return HTMLResponse(PAGE)

    @app.get("/stream.mjpg")
    def stream():
        return StreamingResponse(_mjpeg(feed, 1 / fps), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/state")
    def state():
        if human:
            human.seen()
        frame = feed.latest()
        return {
            **session.state(),
            "prompt": human.prompt.to_dict() if human and human.prompt else None,
            "screen": {"health": feed.health().__dict__, "size": frame.size if frame else None},
            "teach": teach.state() if teach else None,
        }

    # Agent

    @app.post("/task")
    def start(task: str = Body(embed=True)):
        if session.status == "running":
            raise HTTPException(409, "A task is already running")
        if teach and teach.rec and not teach.rec.closed:
            raise HTTPException(409, "A teaching session is open; finish it first")
        if not task.strip():
            raise HTTPException(400, "Empty task")
        session.task, session.plan, session.steps = task.strip(), [], []
        session.status = "running"
        session.stop.clear()
        if human:
            human.stop_event.clear()
        threading.Thread(target=_run, args=(session, new_agent), daemon=True).start()
        return {"ok": True}

    @app.post("/done")
    def press_done():
        if human is None or not human.done():
            raise HTTPException(400, "No move to confirm")
        return {"ok": True}

    @app.post("/answer")
    def answer(text: str = Body(embed=True)):
        session.answer(text)
        return {"ok": True}

    @app.post("/reset")
    def reset():
        if session.status == "running":
            raise HTTPException(409, "Stop the task first")
        session.reset()
        return {"ok": True}

    @app.post("/stop")
    def stop():
        session.stop.set()
        if human and session.status == "running":
            human.stop()
        return {"ok": True}

    # Human actuator prompts

    @app.post("/api/human/prompts/{prompt_id}")
    def answer_prompt(prompt_id: str, result: str = Body("done", embed=True), note: str | None = Body(None, embed=True)):
        if human is None:
            raise TeachError(400, "unsupported", "No human actuator")
        try:
            ok = human.answer(prompt_id, result, (note or "").strip() or None)
        except ValueError as err:
            raise TeachError(400, "bad_request", str(err))
        if not ok:
            raise TeachError(409, "already_answered", "This move is no longer open")
        return {"ok": True}

    # Teaching (docs/human-actuator-teaching-ui.md 4.3)

    @app.get("/api/status")
    def status():
        return {"screen": feed.health().__dict__, "human": human.health().__dict__ if human else None,
                "teach": teach.state() if teach else None}

    @app.get("/api/apps")
    def apps():
        return need_teach().apps()

    @app.get("/api/apps/{app_id}/recordings")
    def app_recordings(app_id: str):
        return need_teach().recordings(app_id)

    @app.post("/api/sessions")
    def open_session(goal: str = Body(...), app_name: str = Body(""), app_id: str = Body(""),
                     bundle_id: str | None = Body(None), mode: str = Body("watch")):
        if session.status == "running":
            raise TeachError(409, "busy", "The agent is running a task; stop it first")
        return {"session_id": need_teach().start(goal, app_name, app_id, bundle_id, mode)}

    @app.post("/api/sessions/{sid}/act")
    def act(sid: str, gesture: dict = Body(...)):
        return need_teach().act(sid, gesture)

    @app.post("/api/sessions/{sid}/drop")
    def drop(sid: str, what: str = Body("input", embed=True)):
        need_teach().drop(sid, what)
        return {"ok": True}

    @app.post("/api/sessions/{sid}/note")
    def note(sid: str, text: str = Body(...), step: int | None = Body(None)):
        return {"step": need_teach().note(sid, text, step)}

    @app.post("/api/sessions/{sid}/mark")
    def mark(sid: str, box: list[float] = Body(...), label: str = Body(...), step: int | None = Body(None)):
        return {"step": need_teach().mark(sid, box, label, step)}

    @app.post("/api/sessions/{sid}/stop")
    def teach_stop(sid: str):
        need_teach().stop(sid)
        return {"ok": True}

    @app.post("/api/sessions/{sid}/resume")
    def teach_resume(sid: str):
        need_teach().resume(sid)
        return {"ok": True}

    @app.post("/api/sessions/{sid}/finish")
    def finish(sid: str, outcome: str = Body(...), note: str | None = Body(None)):
        return {"recording_path": need_teach().finish(sid, outcome, note)}

    @app.get("/api/recordings/{rec_id}")
    def recording(rec_id: str):
        return need_teach().recording(rec_id)

    @app.get("/api/recordings/{rec_id}/frames/{seq}.jpg")
    def recording_frame(rec_id: str, seq: int):
        return Response(need_teach().frame_path(rec_id, seq).read_bytes(), media_type="image/jpeg")

    @app.post("/api/recordings/{rec_id}/skill")
    def write_skill(rec_id: str):
        return {"draft_id": need_teach().start_draft(rec_id)}

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str):
        return need_teach().draft(draft_id)

    @app.put("/api/drafts/{draft_id}")
    def put_draft(draft_id: str, skill_md: str = Body(...), screens: list[dict] | None = Body(None)):
        need_teach().update_draft(draft_id, skill_md, screens)
        return {"ok": True}

    @app.post("/api/drafts/{draft_id}/fix")
    def fix_draft(draft_id: str):
        need_teach().fix_draft(draft_id)
        return {"ok": True}

    @app.get("/api/drafts/{draft_id}/problems")
    def draft_problems(draft_id: str):
        t = need_teach()
        return t.problems(t._draft(draft_id))

    @app.get("/api/drafts/{draft_id}/screens/{name}.jpg")
    def draft_screen(draft_id: str, name: str):
        return Response(need_teach().screen_jpeg(draft_id, name), media_type="image/jpeg")

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(draft_id: str):
        return {"skill_path": need_teach().approve(draft_id)}

    return app


def _run(session: Session, new_agent: Callable[[], Agent]) -> None:
    try:
        new_agent().run(session.task)
    except Exception as err:  # e.g. no mirror window, API error
        session.on_event("error", {"message": str(err)})
    finally:
        if session.status == "running":
            session.status = "stopped" if session.stop.is_set() else "error"


def _mjpeg(feed: FrameFeed, interval: float):
    seq = 0
    while True:
        f = feed.wait_newer(seq, timeout=5)
        if f is None:
            continue  # no mirror yet; keep the connection open
        seq = f.seq
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + f.jpeg + b"\r\n"
        time.sleep(interval / 2)
