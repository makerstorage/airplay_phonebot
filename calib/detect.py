"""Finds the red dot the calibration page draws where it was touched (it shows one dot: the last touch)."""

import numpy as np
from PIL import Image


def find_dot(img: Image.Image, min_pixels: int = 30) -> tuple[float, float] | None:
    """Centroid (phone pixels) of the red pixels, or None if there is no dot."""
    ys, xs = np.nonzero(_is_red(np.asarray(img.convert("RGB"), dtype=np.int16)))
    if len(xs) < min_pixels:
        return None
    return float(xs.mean()), float(ys.mean())


def find_marks(img: Image.Image, min_pixels: int = 30) -> list[tuple[float, float]] | None:
    """Centres (phone pixels) of the four blue corner marks the calibration page draws, in the order
    top-left, top-right, bottom-right, bottom-left; None if they are not all there."""
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    ys, xs = np.nonzero((a[..., 2] > 150) & (a[..., 0] < 90) & (a[..., 1] < 90))
    if len(xs) < 4 * min_pixels:
        return None
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    marks = []
    for right, low in ((False, False), (True, False), (True, True), (False, True)):
        m = ((xs > cx) == right) & ((ys > cy) == low)
        if m.sum() < min_pixels:
            return None
        marks.append((float(xs[m].mean()), float(ys[m].mean())))
    return marks


def _is_red(img: np.ndarray) -> np.ndarray:
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return (r > 150) & (g < 90) & (b < 90)
