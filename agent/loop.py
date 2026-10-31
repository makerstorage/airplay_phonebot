"""The see-think-act loop: Claude Opus 5.5 with the computer toolset, driving the phone."""

import threading
from typing import Any, Callable

import anthropic

from agent.config import AgentConfig
from agent.phone import PhoneEnv, image_block
from agent.prompts import build_system
from agent.skills import Skill

NOT_EXECUTED = "Not executed: an earlier computer action in this turn failed."

# Computer toolset members that make sense on a phone; the rest are switched off
ENABLED = {
    "screenshot", "zoom", "left_click", "double_click", "left_click_drag",
    "mouse_move", "left_mouse_down", "left_mouse_up", "cursor_position", "scroll", "wait",
}
DISABLED = ["right_click", "middle_click", "triple_click", "type", "key", "hold_key"]
PHYSICAL = {"left_click", "double_click", "left_click_drag", "mouse_move",
            "left_mouse_down", "left_mouse_up", "scroll", "home"}

BETAS = [
    "context-management-2025-06-27",   # clear old screenshots server-side
    "server-side-fallback-2026-07-01",  # retry on another model if a request is declined
]


def _strict(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS = [
    {"type": "computer_toolset_20260801", "configs": {m: {"enabled": False} for m in DISABLED}},
    _strict("home", "Go to the iPhone home screen (swipe up from the bottom edge).", {}, []),
    _strict(
        "ask_user",
        "Ask the user a question and wait for the answer. Use it to confirm orders, payments, "
        "messages and other actions that can't be undone, or when information is missing.",
        {"question": {"type": "string"}},
        ["question"],
    ),
    _strict(
        "load_skill",
        "Load a skill (app know-how) by name from the list in the system prompt.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _strict(
        "todo",
        "Write or update your plan. Send the full list every time.",
        {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "done"]},
                    },
                    "required": ["text", "status"],
                    "additionalProperties": False,
                },
            }
        },
        ["items"],
    ),
]
CUSTOM = {"home", "ask_user", "load_skill", "todo"}


class Stopped(Exception):
    pass


class Agent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        cfg: AgentConfig,
        env: PhoneEnv,
        skills: dict[str, Skill],
        ask: Callable[[str], str],
        on_event: Callable[[str, dict], None] = lambda kind, data: None,
        stop: threading.Event | None = None,
    ):
        self.client = client
        self.cfg = cfg
        self.env = env
        self.skills = skills
        self.ask = ask
        self.emit = on_event
        self.stop = stop or threading.Event()
        self.system = build_system(skills)
        self.messages: list[dict] = []

    def run(self, task: str) -> str:
        first = self.env.screenshot()
        self.emit("screenshot", {"image": first})
        self.messages = [{"role": "user", "content": [{"type": "text", "text": task}, image_block(first)]}]
        try:
            for _ in range(self.cfg.max_steps):
                self._check_stop()
                resp = self._call(self.messages)
                # Append the full content unchanged: thinking blocks must be passed back as-is
                self.messages.append({"role": "assistant", "content": resp.content})
                self._emit_content(resp)

                if resp.stop_reason == "refusal":
                    return self._finish("error", "The model declined this request.")
                if resp.stop_reason == "max_tokens":
                    return self._finish("error", "The model's reply was cut off (max_tokens).")
                if resp.stop_reason == "pause_turn":
                    continue

                tool_uses = [b for b in resp.content if b.type == "tool_use"]
                if not tool_uses:
                    text = "\n".join(b.text for b in resp.content if b.type == "text")
                    return self._finish("done", text)
                self.messages.append({"role": "user", "content": self._run_tools(tool_uses)})
            return self._finish("error", f"Stopped after {self.cfg.max_steps} steps.")
        except Stopped:
            return self._finish("stopped", "Stopped by the user.")
        finally:
            self.env.release()  # never leave the stylus on the glass

    # Model call

    def _call(self, messages: list[dict]) -> Any:
        with self.client.beta.messages.stream(
            model=self.cfg.model,
            max_tokens=64000,
            system=self.system,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": self.cfg.effort},
            cache_control={"type": "ephemeral"},
            context_management={
                "edits": [{
                    "type": "clear_tool_uses_20250919",
                    "trigger": {"type": "input_tokens", "value": self.cfg.clear_trigger_tokens},
                    "keep": {"type": "tool_uses", "value": self.cfg.keep_tool_uses},
                    "clear_at_least": {"type": "input_tokens", "value": 10000},
                    "exclude_tools": ["todo", "load_skill", "ask_user"],
                }]
            },
            fallbacks="default",
            betas=BETAS,
        ) as stream:
            return stream.get_final_message()

    # Tools

    def _run_tools(self, tool_uses: list) -> list[dict]:
        """Runs a turn's tool calls in order and stops at the first failure."""
        results: list[dict] = []
        failed = False
        physical = False
        ended_with_image = False
        for block in tool_uses:
            result = {"type": "tool_result", "tool_use_id": block.id}
            if getattr(block, "toolset_name", None) == "computer":
                result["toolset_name"] = "computer"
            if failed:
                result.update(content=NOT_EXECUTED, is_error=True)
                results.append(result)
                continue
            self._check_stop()
            self.emit("action", {"name": block.name, "input": block.input})
            try:
                if block.name in CUSTOM:
                    content = self._run_custom(block.name, block.input)
                else:
                    content = self._run_computer(block.name, block.input)
                result["content"] = content
                physical |= block.name in PHYSICAL
                ended_with_image = block.name in ("screenshot", "zoom")
            except Stopped:
                raise
            except Exception as err:
                result.update(content=f"Error: {err}", is_error=True)
                self.emit("error", {"message": f"{block.name}: {err}"})
                failed = True
            results.append(result)

        # Save a round trip: show the new screen if the turn didn't end with a screenshot
        if physical and not ended_with_image:
            ok = [r for r in results if not r.get("is_error")]
            if ok:
                img = self.env.screenshot()
                self.emit("screenshot", {"image": img})
                last = ok[-1]
                text = last["content"] if isinstance(last["content"], str) else None
                last["content"] = ([{"type": "text", "text": text}] if text else last["content"]) + [image_block(img)]
        return results

    def _run_computer(self, name: str, inp: dict) -> str | list[dict]:
        env = self.env
        coord = inp.get("coordinate")
        if name == "screenshot":
            img = env.screenshot()
            self.emit("screenshot", {"image": img})
            return [image_block(img)]
        if name == "zoom":
            return [image_block(env.zoom(inp["region"]))]
        if name == "left_click":
            env.tap(*(coord or env.cursor))
        elif name == "double_click":
            env.double_tap(*(coord or env.cursor))
        elif name == "left_click_drag":
            env.swipe(*inp["start_coordinate"], *coord)
        elif name == "mouse_move":
            env.move(*coord)
        elif name == "left_mouse_down":
            env.press()
        elif name == "left_mouse_up":
            env.release()
        elif name == "cursor_position":
            x, y = env.cursor
            return f"X={round(x)}, Y={round(y)}"
        elif name == "scroll":
            env.scroll(inp["scroll_direction"], int(inp.get("scroll_amount", 3)), coord)
        elif name == "wait":
            env.sleep(min(float(inp.get("duration", 1)), 30))
        else:
            raise ValueError(f"'{name}' is not available on the phone")
        return "OK"

    def _run_custom(self, name: str, inp: dict) -> str:
        if name == "home":
            self.env.home()
            return "OK"
        if name == "todo":
            self.emit("plan", {"items": inp["items"]})
            return "OK"
        if name == "load_skill":
            skill = self.skills.get(inp["name"])
            if not skill:
                raise ValueError(f"No skill '{inp['name']}'. Available: {', '.join(self.skills) or 'none'}")
            return skill.body
        if name == "ask_user":
            self.emit("ask", {"question": inp["question"]})
            answer = self.ask(inp["question"])
            self.emit("answer", {"answer": answer})
            return f"User answered: {answer}"
        raise ValueError(f"Unknown tool '{name}'")

    # Helpers

    def _emit_content(self, resp: Any) -> None:
        for block in resp.content:
            if block.type == "thinking" and block.thinking:
                self.emit("thinking", {"text": block.thinking})
            elif block.type == "text" and block.text:
                self.emit("text", {"text": block.text})
        usage = getattr(resp, "usage", None)
        if usage:
            self.emit("usage", {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
                "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            })

    def _check_stop(self) -> None:
        if self.stop.is_set():
            raise Stopped()

    def _finish(self, kind: str, text: str) -> str:
        self.emit(kind, {"text": text})
        return text
