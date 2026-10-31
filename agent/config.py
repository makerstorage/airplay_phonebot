from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AgentConfig:
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_steps: int = 80
    settle_s: float = 0.6
    stable_timeout_s: float = 3.0
    clear_trigger_tokens: int = 80000
    keep_tool_uses: int = 12
    skills_dir: str = "skills"


def load_agent_config(path: str | Path = "config.yaml") -> AgentConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return AgentConfig(**data.get("agent", {}))
