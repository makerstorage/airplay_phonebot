"""Skills: markdown files with app know-how, loaded by the agent on demand.

Each file starts with a small header:
---
name: ios_basics
description: one line telling the agent when to load it
---
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    body: str


def load_skills(skills_dir: str | Path) -> dict[str, Skill]:
    skills = {}
    for path in sorted(Path(skills_dir).glob("*.md")):
        text = path.read_text()
        meta, body = {}, text
        if text.startswith("---"):
            _, header, body = text.split("---", 2)
            for line in header.strip().splitlines():
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        name = meta.get("name", path.stem)
        skills[name] = Skill(name, meta.get("description", ""), body.strip())
    return skills
