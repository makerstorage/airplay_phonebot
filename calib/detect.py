"""Finds the new red dot the calibration page drew after a tap."""

import numpy as np
from PIL import Image


def find_new_dot(before: Image.Image, after: Image.Image, min_pixels: int = 30) -> tuple[float, float] | None:
    """Centroid (phone pixels) of red pixels in `after` that weren't red in `before`."""
    b = np.asarray(before.convert("RGB"), dtype=np.int16)
    a = np.asarray(after.convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return None
    new_red = _is_red(a) & ~_is_red(b)
    ys, xs = np.nonzero(new_red)
    if len(xs) < min_pixels:
        return None
    return float(xs.mean()), float(ys.mean())


def _is_red(img: np.ndarray) -> np.ndarray:
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return (r > 150) & (g < 90) & (b < 90)
