"""Captures the iPhone screen from the macOS AirPlay Receiver window.

Pixel spaces:
- phone pixels: the cropped, full-resolution phone image (calibration uses this)
- model pixels: the downscaled image sent to the LLM
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import Quartz
import yaml
from PIL import Image


@dataclass
class VisionConfig:
    window_owner: str = "Control Center"  # substring of the window's owner app name
    max_long_edge: int = 1280             # downscale target for the LLM image
    phone_width: int = 1179               # iPhone screen resolution, used for its aspect ratio
    phone_height: int = 2556


def load_vision_config(path: str | Path = "config.yaml") -> VisionConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return VisionConfig(**data.get("vision", {}))


@dataclass
class Frame:
    phone: Image.Image  # cropped, full resolution
    model: Image.Image  # downscaled for the LLM
    scale: float        # model pixels / phone pixels

    def to_phone(self, x: float, y: float) -> tuple[float, float]:
        """Model pixel -> phone pixel (per axis, so size rounding adds no error)."""
        return x * self.phone.width / self.model.width, y * self.phone.height / self.model.height

    @classmethod
    def from_phone(cls, phone: Image.Image, max_long_edge: int) -> "Frame":
        scale = min(1.0, max_long_edge / max(phone.size))
        size = (round(phone.width * scale), round(phone.height * scale))
        model = phone.resize(size, Image.LANCZOS) if scale < 1.0 else phone.copy()
        return cls(phone=phone, model=model, scale=scale)


def list_windows() -> list[dict]:
    infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
    )
    return [
        {
            "id": int(w["kCGWindowNumber"]),
            "owner": str(w.get("kCGWindowOwnerName", "")),
            "name": str(w.get("kCGWindowName", "") or ""),
            "bounds": dict(w["kCGWindowBounds"]),
        }
        for w in infos
    ]


class ScreenCapture:
    def __init__(self, cfg: VisionConfig):
        self.cfg = cfg

    def find_window(self) -> int:
        matches = [w for w in list_windows() if self.cfg.window_owner.lower() in w["owner"].lower()]
        if not matches:
            raise RuntimeError(
                f"No window from an app matching '{self.cfg.window_owner}'. "
                "Is the iPhone mirroring to this Mac? Run `uv run python -m vision --list`."
            )
        # The largest window is the mirrored screen
        return max(matches, key=lambda w: w["bounds"]["Width"] * w["bounds"]["Height"])["id"]

    def grab(self) -> Frame:
        raw = self._capture_window(self.find_window())
        return Frame.from_phone(self._crop_phone(raw), self.cfg.max_long_edge)

    def _capture_window(self, window_id: int) -> Image.Image:
        # `screencapture` needs the Screen Recording permission for the terminal/app
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            subprocess.run(
                ["screencapture", "-x", "-o", "-l", str(window_id), f.name],
                check=True,
            )
            return Image.open(f.name).convert("RGB")

    def _crop_phone(self, img: Image.Image) -> Image.Image:
        # Fullscreen mirroring centers the phone and fits it to the window.
        # A fixed box from the aspect ratio keeps the crop stable for calibration.
        aspect = self.cfg.phone_width / self.cfg.phone_height
        h = img.height
        w = round(h * aspect)
        if w > img.width:
            w = img.width
            h = round(w / aspect)
        left = (img.width - w) // 2
        top = (img.height - h) // 2
        return img.crop((left, top, left + w, top + h))
