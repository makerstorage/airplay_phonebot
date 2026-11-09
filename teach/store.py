"""Where recordings and skills live on disk, and how to find them."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TeachConfig:
    recordings_dir: str = "recordings"
    skills_dir: str = "skills"
    device_profile: str = "iphone-13-pro"
    os: str = "ios"
    prompt_timeout_s: float | None = None   # None = a human prompt waits forever while teaching
    settle_quiet_s: float = 0.6             # screen still for this long = settled
    settle_most_s: float = 4.0              # give up waiting for a still screen after this long
    change_threshold: float = 2.0           # mean grey difference that counts as a screen change
    skill_writer: dict = field(default_factory=lambda: {
        "model": "claude-opus-5-5", "effort": "high", "max_frames": 60,
    })


def load_teach_config(path: str | Path = "config.yaml") -> TeachConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    cfg = TeachConfig(**{k: v for k, v in (data.get("teach") or {}).items() if k != "skill_writer"})
    cfg.skill_writer.update((data.get("teach") or {}).get("skill_writer") or {})
    return cfg


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:64] or "app"


def list_apps(rec_root: Path, skills_root: Path) -> list[dict]:
    apps: dict[str, dict] = {}
    for d in sorted(Path(rec_root).glob("*")):
        if d.is_dir():
            recs = [r for r in d.iterdir() if (r / "session.json").exists()]
            name = d.name
            if recs:
                name = json.loads((recs[-1] / "session.json").read_text())["app"].get("name", d.name)
            apps[d.name] = {"app_id": d.name, "name": name, "bundle_id": None, "skill": False,
                            "recordings": len(recs)}
    for d in sorted(Path(skills_root).glob("*/SKILL.md")):
        app_id = d.parent.name
        apps.setdefault(app_id, {"app_id": app_id, "name": app_id, "bundle_id": None, "recordings": 0})
        apps[app_id]["skill"] = True
    return list(apps.values())


def list_recordings(rec_root: Path, app_id: str) -> list[dict]:
    out = []
    for r in sorted((Path(rec_root) / app_id).glob("*/session.json"), reverse=True):
        s = json.loads(r.read_text())
        out.append({"id": s["session_id"], "goal": s["goal"], "outcome": s["outcome"],
                    "started": s["started"], "finished": s["finished"]})
    return out


def find_recording(rec_root: Path, rec_id: str) -> Path | None:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", rec_id):
        return None
    hits = list(Path(rec_root).glob(f"*/{rec_id}/session.json"))
    return hits[0].parent if hits else None


def load_recording(path: Path) -> tuple[dict, list[dict]]:
    session = json.loads((path / "session.json").read_text())
    events_file = path / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().splitlines() if line.strip()] \
        if events_file.exists() else []
    return session, events
