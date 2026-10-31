"""Control page: live phone screen, the move to do drawn on it, task / plan / steps / ask / stop."""

import io
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from actuator import Intent
from agent import Agent
from agent.phone import FrameSource

PAGE = (Path(__file__).parent / "page.html").read_text()
MAX_STEPS_SHOWN = 300


class Session:
    """State shared by the agent thread and the web page."""

    def __init__(self, mode: str):
        self.mode = mode
        self.status = "idle"  # idle | running | done | stopped | error
        self.task = ""
        self.plan: list[dict] = []
        self.steps: list[dict] = []
        self.intent: Intent | None = None
        self.question: str | None = None
        self.phone_size: tuple[int, int] | None = None
        self.stop = threading.Event()
        self._answers: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()

    # Called from the agent thread

    def show_intent(self, intent: Intent | None) -> None:
        self.intent = intent

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
        self.intent = self.question = None

    def state(self) -> dict:
        return {
            "mode": self.mode,
            "status": self.status,
            "task": self.task,
            "plan": self.plan,
            "steps": self.steps,
            "intent": asdict(self.intent) if self.intent else None,
            "question": self.question,
            "phone_size": self.phone_size,
        }

    def _add_step(self, kind: str, text: str) -> None:
        with self._lock:
            self.steps.append({"kind": kind, "text": text, "t": time.time()})
            del self.steps[:-MAX_STEPS_SHOWN]


def create_app(
    capture: FrameSource,
    session: Session,
    new_agent: Callable[[], Agent],
    done: Callable[[], None] | None = None,
    fps: float = 5,
) -> FastAPI:
    """new_agent builds a fresh Agent per task; done is the human actuator's Done (None in gcode mode)."""
    app = FastAPI()

    @app.get("/")
    def index():
        return HTMLResponse(PAGE)

    @app.get("/stream.mjpg")
    def stream():
        return StreamingResponse(_mjpeg(capture, session, 1 / fps),
                                 media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/state")
    def state():
        return session.state()

    @app.post("/task")
    def start(task: str = Body(embed=True)):
        if session.status == "running":
            raise HTTPException(409, "A task is already running")
        if not task.strip():
            raise HTTPException(400, "Empty task")
        session.task, session.plan, session.steps = task.strip(), [], []
        session.status = "running"
        session.stop.clear()
        threading.Thread(target=_run, args=(session, new_agent), daemon=True).start()
        return {"ok": True}

    @app.post("/done")
    def press_done():
        if done is None:
            raise HTTPException(400, "Not in human mode")
        done()
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
        return {"ok": True}

    return app


def _run(session: Session, new_agent: Callable[[], Agent]) -> None:
    try:
        new_agent().run(session.task)
    except Exception as err:  # e.g. no mirror window, API error
        session.on_event("error", {"message": str(err)})
    finally:
        session.intent = None
        if session.status == "running":
            session.status = "stopped" if session.stop.is_set() else "error"


def _mjpeg(capture: FrameSource, session: Session, interval: float):
    while True:
        start = time.monotonic()
        try:
            img = capture.grab().phone
        except RuntimeError:
            # No mirror window yet; keep the connection open and try again
            time.sleep(1)
            continue
        session.phone_size = img.size
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n"
        time.sleep(max(0.0, interval - (time.monotonic() - start)))
