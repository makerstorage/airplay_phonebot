"""Checks a skill draft before it is shown and again on Approve (docs/human-actuator-teaching-ui.md 4.6)."""

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from teach.store import find_recording

REQUIRED_SECTIONS = ["## Hard rules", "## Screens", "## Tasks", "## Pitfalls"]
IRREVERSIBLE = ["send", "delete", "pay", "submit", "purchase", "order", "sign out", "remove"]
INFERRED_TAG = "(inferred)"


@dataclass
class Problem:
    level: str   # error | warning
    check: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def split_front_matter(md: str) -> tuple[dict | None, str]:
    if not md.startswith("---"):
        return None, md
    parts = md.split("---", 2)
    if len(parts) < 3:
        return None, md
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, md
    return (meta if isinstance(meta, dict) else None), parts[2]


def _section(body: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m.group(1) if m else ""


def validate_skill(app_id: str, skill_md: str, screens: list[dict], sources: list[str],
                   rec_root: Path) -> list[Problem]:
    p: list[Problem] = []
    err = lambda check, detail: p.append(Problem("error", check, detail))  # noqa: E731
    warn = lambda check, detail: p.append(Problem("warning", check, detail))  # noqa: E731

    meta, body = split_front_matter(skill_md)
    if meta is None:
        err("front_matter", "SKILL.md must start with a YAML front matter block between --- lines")
        meta = {}

    name = str(meta.get("name", ""))
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        err("name", "name must be lowercase letters, digits and hyphens, at most 64 characters")
    if name and name != app_id:
        err("name", f"name '{name}' must equal the folder name '{app_id}'")

    desc = str(meta.get("description", "") or "")
    if not desc:
        err("description", "description is missing")
    else:
        if len(desc) > 400:
            err("description", f"description is {len(desc)} characters, at most 400")
        if "Use when" not in desc:
            err("description", "description must say when to use it ('Use when ...')")
        if "Triggers:" not in desc:
            err("description", "description must end with a 'Triggers:' list")

    app = meta.get("app") if isinstance(meta.get("app"), dict) else {}
    if not app.get("name"):
        err("app", "app.name is missing")
    tasks = meta.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        err("tasks", "tasks must be a non-empty list of task ids")
        tasks = []
    for t in tasks:
        if not re.search(rf"^### {re.escape(str(t))}\s*$", body, re.M):
            err("tasks", f"task '{t}' has no '### {t}' section")

    for s in REQUIRED_SECTIONS:
        if not re.search(rf"^{re.escape(s)}\s*$", body, re.M):
            err("sections", f"missing section '{s}'")

    names = {s["name"] for s in screens}
    linked = set(re.findall(r"\]\(screens/([^)\s]+)\.jpg\)", body))
    for n in sorted(linked - names):
        err("screens", f"image link screens/{n}.jpg has no screen")
    for n in sorted(names - linked):
        warn("screens", f"screen '{n}' is not linked from SKILL.md; it will not be saved")

    for rid in sources:
        if not find_recording(rec_root, rid):
            err("sources", f"recording '{rid}' does not exist")

    hard = _section(body, "## Hard rules").lower()
    task_text = _section(body, "## Tasks").lower()
    for word in IRREVERSIBLE:
        if re.search(rf"\b{word}\b", task_text) and not re.search(rf"\b{word}\b", hard):
            warn("hard_rules", f"a step mentions '{word}' but no hard rule covers it")

    lines = skill_md.count("\n") + 1
    if lines > 500:
        warn("length", f"SKILL.md is {lines} lines, keep it under 500")
    if INFERRED_TAG in skill_md:
        warn("inferred", f"{skill_md.count(INFERRED_TAG)} step(s) still marked {INFERRED_TAG}: check them")
    return p
