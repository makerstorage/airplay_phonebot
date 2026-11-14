import numpy as np
from PIL import Image, ImageDraw

from calib import Calibration, apply_homography, fit_homography
import pytest

from calib.run import CalibConfig, CalibError, calibrate, search_points

# A "true" mapping: machine mm -> phone pixels, slightly rotated and scaled
TRUE_MM_TO_PX = np.array([[12.0, 0.4, 30.0], [-0.3, 12.1, 20.0], [0.0, 0.0, 1.0]])


def test_fit_recovers_mapping():
    mm = [(0, 0), (70, 0), (70, 150), (0, 150), (35, 75)]
    px = [apply_homography(TRUE_MM_TO_PX, *p) for p in mm]
    h = fit_homography(px, mm)
    for p, m in zip(px, mm):
        assert np.allclose(apply_homography(h, *p), m, atol=1e-6)


class FakePhone:
    """A phone lying somewhere on the machine, showing the calibration page. The page is the image
    scaled down 3x and starts 40 page pixels below the top (Safari's bar). A tap on the page is
    reported as a touch and shows one red dot; the page draws the blue corner marks it is told to."""

    def __init__(self, mm_to_px=TRUE_MM_TO_PX, size=(1170, 2532)):
        self.mm_to_px, self.size = mm_to_px, size
        self.touches = []
        self.taps = []
        self.view = {}
        self.dot = None          # image pixel of the last touch
        self.deaf = set()        # tap numbers (1-based) that do not register

    def to_image(self, x, y):
        return x * 3, (y + 40) * 3

    def page(self):
        return {"w": self.size[0] / 3, "h": self.size[1] / 3 - 80}

    def tap(self, x, y):
        self.taps.append((x, y))
        px, py = apply_homography(self.mm_to_px, x, y)
        on_page = 0 <= px < self.size[0] and 120 <= py < self.size[1] - 120
        if on_page and len(self.taps) not in self.deaf:
            self.touches.append((px / 3, py / 3 - 40))
            self.dot = (px, py)

    def grab(self):
        img = Image.new("RGB", self.size, "white")
        draw = ImageDraw.Draw(img)
        for m in self.view.get("marks") or []:
            x, y = self.to_image(*m)
            draw.rectangle([x - 40, y - 40, x + 40, y + 40], fill="blue")
        if self.dot:
            draw.ellipse([self.dot[0] - 30, self.dot[1] - 30, self.dot[0] + 30, self.dot[1] + 30], fill="red")
        return img

    def show(self, view):
        self.view = view
        self.views.append(view)

    def run(self, **kw):
        self.views = []
        cfg = CalibConfig(settle_s=0)
        return calibrate(self.tap, self.grab, lambda: self.touches, 200, 250, cfg, say=lambda _: None,
                         show=self.show, page=self.page, **kw)


def test_calibrate_finds_the_screen_and_fits(tmp_path):
    phone = FakePhone()  # slightly turned, part of the screen is outside the work area
    calib = phone.run()
    assert calib.error_mm < 0.1
    inv = np.linalg.inv(TRUE_MM_TO_PX)
    xs, ys = zip(*[apply_homography(inv, *c) for c in ((0, 0), (1170, 0), (1170, 2532), (0, 2532))])
    assert calib.screen_box == pytest.approx([min(xs), min(ys), max(xs), max(ys)], abs=0.2)
    assert all(0 <= x <= 200 and 0 <= y <= 250 for x, y in phone.taps)

    calib.save(tmp_path / "c.json")
    loaded = Calibration.load(tmp_path / "c.json")
    px = apply_homography(TRUE_MM_TO_PX, 40, 100)
    assert np.allclose(loaded.to_machine(*px), (40, 100), atol=0.1)
    assert loaded.screen_box == calib.screen_box


def test_calibrate_handles_a_turned_phone_away_from_the_middle():
    # Phone turned 180 degrees with its screen at x 120..185, y 20..160 mm: the middle of the area misses it
    k = 18.0
    phone = FakePhone(np.array([[-k, 0, 185 * k], [0, -k, 160 * k], [0, 0, 1.0]]))
    calib = phone.run()
    assert calib.error_mm < 0.1
    assert calib.screen_box == pytest.approx([120, 19.3, 185, 160], abs=1.5)
    assert len(phone.taps) > 12  # some search taps missed first


def test_calibrate_starts_at_the_seed():
    phone = FakePhone()
    phone.run(seed=(50, 100))
    assert phone.taps[0] == (50, 100)
    assert len(phone.taps) == 21  # 1 search + 2 probes + 9 targets + 9 check taps


def test_calibrate_without_phone_fails_and_can_be_stopped():
    phone = FakePhone(np.array([[12.0, 0, -99999], [0, 12.0, 0], [0, 0, 1.0]]))
    with pytest.raises(CalibError, match="No tap reached"):
        phone.run()
    assert len(phone.taps) == len(search_points(200, 250, CalibConfig()))
    with pytest.raises(CalibError, match="Stopped"):
        FakePhone().run(stop=lambda: True)


def test_search_points_cover_the_area_inside_the_edges():
    pts = search_points(200, 200, CalibConfig())
    assert pts[0] == (100, 100)
    assert len(pts) == 25 and all(10 <= x <= 190 and 10 <= y <= 190 for x, y in pts)


def test_check_round_measures_every_target_and_the_page_gets_them():
    phone = FakePhone()
    calib = phone.run(seed=(50, 100))
    targets = calib.check["targets"]
    assert len(targets) == 9 and all(t["state"] == "hit" and t["err_mm"] < 0.2 for t in targets)
    assert calib.check["px_per_mm"] == pytest.approx([4.0, 4.03], abs=0.02)  # 12 image pixels per mm / 3
    # The page is told where its targets are, in its own pixels; the check is drawn in image pixels
    last = phone.views[-1]
    assert last["title"].startswith("Check: 9 of 9") and last["round"] == 1 and last["marks"] == []
    w, h = phone.page()["w"], phone.page()["h"]
    assert (last["targets"][0]["x"], last["targets"][0]["y"]) == pytest.approx((0.15 * w, 0.15 * h))
    assert targets[0]["px"] == pytest.approx(phone.to_image(0.15 * w, 0.15 * h), abs=1)
    assert targets[0]["dot"] == pytest.approx(targets[0]["px"], abs=2)


def test_taps_that_do_not_register_are_tried_again():
    phone = FakePhone()
    phone.deaf = {2, 6, 15}  # a probe, a target and a check tap give no touch
    calib = phone.run(seed=(50, 100))
    assert calib.error_mm < 0.1
    assert all(t["state"] == "hit" for t in calib.check["targets"])
    assert len(phone.taps) == 24  # 21 + one more for each deaf tap


def test_a_touch_in_the_wrong_place_is_dropped():
    phone = FakePhone()
    real_tap = phone.tap

    def tap(x, y):  # the 6th tap is reported 50 page pixels (12 mm) away, e.g. a finger at the same moment
        real_tap(x, y)
        if len(phone.taps) == 6:
            px, py = phone.touches[-1]
            phone.touches[-1] = (px + 50, py)
            phone.dot = phone.to_image(px + 50, py)

    phone.tap = tap
    calib = phone.run(seed=(50, 100))
    assert calib.error_mm < 0.1
    assert all(t["state"] == "hit" for t in calib.check["targets"])


def test_no_page_or_no_mirror_stops_before_any_tap():
    phone = FakePhone()
    phone.page = lambda: None
    with pytest.raises(CalibError, match="not open"):
        phone.run()
    phone = FakePhone()
    phone.grab = lambda: Image.new("RGB", phone.size, "white")  # the mirror shows something else
    with pytest.raises(CalibError, match="corner marks"):
        phone.run()
    assert phone.taps == []
