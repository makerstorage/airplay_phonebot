"""Skills: markdown files with app know-how, loaded by the agent on demand.

Two layouts in skills_dir:
- skills/<name>.md            a single file (e.g. ios_basics.md)
- skills/<app_id>/SKILL.md    a folder written by the Teach tab, with screens/ and sources.json

Each file starts with a YAML header:
---
name: ios_basics
description: one line telling the agent when to load it
---
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    body: str


def _parse(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            try:
                meta = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                meta = None
            if isinstance(meta, dict):
                return meta, parts[2]
    return {}, text


def load_skills(skills_dir: str | Path) -> dict[str, Skill]:
    skills = {}
    root = Path(skills_dir)
    paths = sorted(root.glob("*.md")) + sorted(root.glob("*/SKILL.md"))
    for path in paths:
        meta, body = _parse(path.read_text())
        default = path.parent.name if path.name == "SKILL.md" else path.stem
        name = str(meta.get("name") or default)
        skills[name] = Skill(name, str(meta.get("description", "")), body.strip())
    return skills
