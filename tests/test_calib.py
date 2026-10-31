import numpy as np
from PIL import Image, ImageDraw

from calib import Calibration, apply_homography, fit_homography
from calib.run import CalibConfig, calibrate, grid_points

# A "true" mapping: machine mm -> phone pixels, slightly rotated and scaled
TRUE_MM_TO_PX = np.array([[12.0, 0.4, 30.0], [-0.3, 12.1, 20.0], [0.0, 0.0, 1.0]])


def test_fit_recovers_mapping():
    mm = [(0, 0), (70, 0), (70, 150), (0, 150), (35, 75)]
    px = [apply_homography(TRUE_MM_TO_PX, *p) for p in mm]
    h = fit_homography(px, mm)
    for p, m in zip(px, mm):
        assert np.allclose(apply_homography(h, *p), m, atol=1e-6)


def test_calibrate_with_simulated_phone(tmp_path):
    screen = Image.new("RGB", (1170, 2532), "white")

    def tap(x, y):
        px, py = apply_homography(TRUE_MM_TO_PX, x, y)
        ImageDraw.Draw(screen).ellipse([px - 30, py - 30, px + 30, py + 30], fill="red")

    cfg = CalibConfig(screen_box=[0, 0, 90, 200], grid=3)
    calib = calibrate(tap, lambda: screen.copy(), grid_points(cfg), settle_s=0)
    assert calib.error_mm < 0.1

    calib.save(tmp_path / "c.json")
    loaded = Calibration.load(tmp_path / "c.json")
    px = apply_homography(TRUE_MM_TO_PX, 40, 100)
    assert np.allclose(loaded.to_machine(*px), (40, 100), atol=0.1)
