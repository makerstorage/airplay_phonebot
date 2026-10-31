"""Homography between phone pixels and machine mm."""

import json
from pathlib import Path

import numpy as np


def _normalize(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # Hartley normalization: center at 0, mean distance sqrt(2)
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
    return (np.c_[pts, np.ones(len(pts))] @ t.T)[:, :2], t


def fit_homography(src: list, dst: list) -> np.ndarray:
    """Least-squares homography mapping src points to dst points (4+ pairs)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if len(src) < 4 or len(src) != len(dst):
        raise ValueError("Need 4 or more matching point pairs")
    s, ts = _normalize(src)
    d, td = _normalize(dst)
    rows = []
    for (x, y), (u, v) in zip(s, d):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.array(rows))
    h = vt[-1].reshape(3, 3)
    h = np.linalg.inv(td) @ h @ ts
    return h / h[2, 2]


def apply_homography(h: np.ndarray, x: float, y: float) -> tuple[float, float]:
    u, v, w = h @ np.array([x, y, 1.0])
    return u / w, v / w


class Calibration:
    """Saved mapping: phone pixel -> machine mm."""

    def __init__(self, h: np.ndarray, error_mm: float = 0.0):
        self.h = h
        self.error_mm = error_mm

    @classmethod
    def from_box(cls, phone_w: float, phone_h: float, box: list[float]) -> "Calibration":
        """Stand-in for dry runs: stretch the phone image over the screen box."""
        x0, y0, x1, y1 = box
        corners = [(0, 0), (phone_w, 0), (phone_w, phone_h), (0, phone_h)]
        return cls(fit_homography(corners, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))

    def to_machine(self, x: float, y: float) -> tuple[float, float]:
        return apply_homography(self.h, x, y)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"h": self.h.tolist(), "error_mm": self.error_mm}, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        data = json.loads(Path(path).read_text())
        return cls(np.array(data["h"]), data.get("error_mm", 0.0))
