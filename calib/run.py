"""Calibration: the machine finds the phone screen itself, then fits phone pixel -> machine mm.

The iPhone shows the calibration page (calib/page.html). Three spaces are tied together:
  image pixels (the AirPlay mirror)  <->  page pixels (the web page)  <->  machine mm
The page reports every touch in its own pixels: that is the measurement (exact, no lag). The mirror is
used for what only it can tell: where the page is in the image, and that each touch really shows there.
  0. marks:   no taps. The page draws four blue corner marks; finding them in the mirror gives
              image <-> page, and proves the page is open and the mirror is live.
  1. search:  tap around the work area until the page reports a touch
  2. probe:   tap a little further in X and in Y -> rough page <-> mm map (direction and scale)
  3. targets: the page draws targets; aim at them nearest first. Every touch corrects the map before
              the next move. A tap may not register: targets without a touch are tried again.
  4. check:   tap every target once more with the final map and measure how far each touch is off.
Every tap is logged, and every touch is looked up in the mirror.
The caller shows the check to the user and asks if it is OK before saving.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import yaml
from PIL import Image

from calib.detect import find_dot, find_marks
from calib.homography import Calibration, apply_homography, fit_affine
from robot.config import RobotConfig

Point = tuple[float, float]


class CalibError(RuntimeError):
    pass


@dataclass
class CalibConfig:
    port: int = 8765
    grid: int = 3              # grid x grid taps
    margin: float = 0.15       # keep grid taps this fraction away from the screen edges
    settle_s: float = 1.0      # wait for the AirPlay image to update after a tap
    search_step: float = 40.0  # mm between search taps (must be smaller than the screen is wide)
    probe_mm: float = 20.0     # how far the two probe taps are from the first hit
    mirror_px: float = 25.0    # a touch must show in the mirror image this close to where the page says it was
    edge_mm: float = 10.0      # search taps keep this far from the work area limits
    search_start: list[float] | None = None  # [x, y] mm of the first search tap when there is no saved screen box (default: the middle)
    outlier_mm: float = 3.0    # a tap that fits the map worse than this was read wrong: dropped from the fit
    ok_mm: float = 2.0         # check round: a dot this close to its target is good (the tip is 9x7 mm)
    file: str = "calib.json"   # set per machine: calibrations/<machine>.json


def load_calib_config(machine: RobotConfig, path: str | Path = "config.yaml") -> CalibConfig:
    """Calibration settings from config.yaml; the result file comes from the machine."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return CalibConfig(**{**data.get("calib", {}), "file": str(machine.calib_file)})


def search_points(x_max: float, y_max: float, cfg: CalibConfig, seed: Point | None = None) -> list[Point]:
    """Points covering the work area every search_step mm, nearest to `seed` first
    (default: cfg.search_start, else the middle)."""
    seed = seed or cfg.search_start or (x_max / 2, y_max / 2)

    def axis(start: float, top: float) -> list[float]:
        lo, hi = cfg.edge_mm, top - cfg.edge_mm
        start = min(max(start, lo), hi)
        steps = np.arange(-np.floor((start - lo) / cfg.search_step), np.floor((hi - start) / cfg.search_step) + 1)
        return [float(start + k * cfg.search_step) for k in steps]

    points = [(x, y) for y in axis(seed[1], y_max) for x in axis(seed[0], x_max)]
    return sorted(points, key=lambda p: np.hypot(p[0] - seed[0], p[1] - seed[1]))


def robust_fit(src: list, mm: list, outlier_mm: float) -> tuple[np.ndarray, float]:
    """Affine fit to machine mm that drops wrong taps (worst first). Returns the map and its RMS error."""
    src, mm = list(src), list(mm)
    while True:
        m = fit_affine(src, mm)
        res = [float(np.hypot(*np.subtract(apply_homography(m, *p), q))) for p, q in zip(src, mm)]
        worst = int(np.argmax(res))
        if len(src) <= 4 or res[worst] <= outlier_mm:
            return m, float(np.sqrt(np.mean(np.square(res))))
        del src[worst], mm[worst]


def calibrate(
    tap: Callable[[float, float], None],
    grab: Callable[[], Image.Image],
    touches: Callable[[], list[Point]],
    x_max: float,
    y_max: float,
    cfg: CalibConfig,
    seed: Point | None = None,
    say: Callable[[str], None] = print,
    stop: Callable[[], bool] = lambda: False,
    debug_dir: Path | None = None,
    show: Callable[[dict], None] = lambda view: None,
    page: Callable[[], dict | None] = lambda: None,
) -> Calibration:
    """tap(x, y) taps at machine mm; grab() returns the phone image; touches() lists the touches the
    calibration page has seen (page pixels); show(view) tells the page what to draw; page() is the
    page's viewport {"w", "h"} or None if it is not open. `seed` is where to look first (e.g. the middle
    of the last screen box). The result carries the check round (.check)."""
    count = 0
    page_hits: list[Point] = []  # where the page was touched
    mm_hits: list[Point] = []    # where the machine tapped
    targets: list[dict] = []
    view: dict = {"round": 0, "title": "", "targets": [], "marks": [], "ruler": None}

    def publish(title: str, **more) -> None:
        view.update(title=title, **more)
        view["targets"] = [{"x": t["page"][0], "y": t["page"][1], "state": t["state"], "err_mm": t["err_mm"]}
                           for t in targets]
        show(dict(view))

    def check_stop() -> None:
        if stop():
            raise CalibError("Stopped")

    # 0. Corner marks: where is the page in the mirror image? No taps yet.
    check_stop()
    info = page()
    if not info:
        raise CalibError("The calibration page is not open on the iPhone (it does not call in). Open or reload it.")
    pw, ph = info["w"], info["h"]
    lo, hi = cfg.margin, 1 - cfg.margin
    marks = [(lo * pw, lo * ph), (hi * pw, lo * ph), (hi * pw, hi * ph), (lo * pw, hi * ph)]
    publish("Reading the screen...", marks=marks)
    to_img = None
    for _ in range(6):
        time.sleep(cfg.settle_s)
        check_stop()
        img = grab()
        found = find_marks(img)
        if found:
            fit = fit_affine(marks, found)
            off = max(np.hypot(*np.subtract(apply_homography(fit, *m), f)) for m, f in zip(marks, found))
            small, big = sorted(np.linalg.svd(fit[:2, :2], compute_uv=False))
            if off <= 4 and small > 0.97 * big:
                to_img = fit
                break
    if debug_dir:
        img.save(debug_dir / "calib_marks.png")
    if to_img is None:
        publish("The mirror does not show this page")
        raise CalibError("The mirror image does not show the calibration page's corner marks. "
                         "Is the iPhone mirroring to this Mac, with the page in front?")
    to_page = np.linalg.inv(to_img)
    w, h = img.size
    say(f"Page found in the mirror: {pw:.0f} x {ph:.0f} page pixels, {np.sqrt(abs(np.linalg.det(to_img[:2, :2]))):.2f} image pixels each")
    publish("Looking for the stylus...", marks=[])

    def try_tap(x: float, y: float) -> Point | None:
        """Taps and returns where the page was touched (page pixels), or None if it reported no touch."""
        nonlocal count
        check_stop()
        count += 1
        before = len(touches())
        tap(x, y)
        new: list[Point] = []
        for _ in range(max(1, round(cfg.settle_s / 0.1))):  # the page reports within a moment
            new = touches()[before:]
            if new:
                time.sleep(min(0.3, cfg.settle_s))  # one tap can touch more than once: take them all
                new = touches()[before:]
                break
            time.sleep(0.1)
        if not new:
            say(f"tap {count} at ({x:.1f}, {y:.1f}) mm: no touch")
            return None
        hit = (float(np.median([p[0] for p in new])), float(np.median([p[1] for p in new])))
        # Look the touch up in the mirror: the red dot must be where the page says it was touched
        want, seen = apply_homography(to_img, *hit), False
        for _ in range(3):
            time.sleep(cfg.settle_s)
            img = grab()
            dot = find_dot(img)
            if dot and np.hypot(*np.subtract(dot, want)) <= cfg.mirror_px:
                seen = True
                break
        if debug_dir:
            img.save(debug_dir / f"calib_{count}.png")
        say(f"tap {count} at ({x:.1f}, {y:.1f}) mm: touch at page ({hit[0]:.0f}, {hit[1]:.0f})"
            + ("" if seen else ", NOT seen there in the mirror") + (f", {len(new)} touches" if len(new) > 1 else ""))
        return hit if seen else None

    def learn(x: float, y: float) -> Point | None:
        hit = try_tap(x, y)
        if hit:
            page_hits.append(hit)
            mm_hits.append((x, y))
        return hit

    def inside(x: float, y: float) -> bool:
        return 0 <= x <= x_max and 0 <= y <= y_max

    # 1. Search for the screen
    say("Looking for the phone screen...")
    for x0, y0 in search_points(x_max, y_max, cfg, seed):
        if learn(x0, y0):
            break
    else:
        publish("No tap reached this page")
        raise CalibError("No tap reached the calibration page. If the stylus came down over the screen, "
                         "it does not reach the glass: lift the phone.")

    # 2. Probe in X and in Y: a first rough map. A tap may not register, so each is tried twice.
    def probe(dx: float, dy: float) -> None:
        for _ in range(2):
            for sign in (1, -1):
                x, y = x0 + sign * dx, y0 + sign * dy
                if inside(x, y) and learn(x, y):
                    return
        raise CalibError(f"Found the screen at ({x0:.1f}, {y0:.1f}) mm but the probe taps next to it gave no touch")

    probe(cfg.probe_mm, 0)
    probe(0, cfg.probe_mm)
    a, b = np.subtract(page_hits[1], page_hits[0]), np.subtract(page_hits[2], page_hits[0])
    if abs(a[0] * b[1] - a[1] * b[0]) < 100:
        raise CalibError("The probe taps gave no usable direction (touches too close together)")

    def fit() -> tuple[np.ndarray, float, dict]:
        """page pixel -> mm from all touches so far, its RMS error, and the machine axes for the page's ruler."""
        m, rms = robust_fit(page_hits, mm_hits, cfg.outlier_mm)
        px_per_mm = np.linalg.inv(m[:2, :2])  # columns: machine +X and +Y in page pixels per mm
        ruler = {"o": [pw / 2, ph / 2], "x": (px_per_mm[:, 0] * 10).tolist(), "y": (px_per_mm[:, 1] * 10).tolist()}
        return m, rms, ruler

    # 3. Targets over the page. Nearest to what is already known first; every touch corrects the map.
    fractions = np.linspace(cfg.margin, 1 - cfg.margin, cfg.grid)
    targets = [{"page": (float(fx * pw), float(fy * ph)), "state": "todo", "hit": None, "err_mm": None}
               for fy in fractions for fx in fractions]

    def aim(t: dict, m: np.ndarray, tapper: Callable[[float, float], Point | None]) -> None:
        """Taps where the map says the target is and notes how far off the touch is."""
        x, y = apply_homography(m, *t["page"])
        if not inside(x, y):
            t.update(state="outside", hit=None, err_mm=None)
            return
        hit = tapper(x, y)
        if hit is None:
            t.update(state="miss", hit=None, err_mm=None)
            return
        err = float(np.hypot(*np.subtract(hit, t["page"])) * np.sqrt(abs(np.linalg.det(m[:2, :2]))))
        t.update(state="hit" if err <= cfg.ok_mm else "off", hit=hit, err_mm=round(err, 2))

    for state in ("todo", "miss"):  # second pass: the ones that gave no touch, with the better map
        while todo := [t for t in targets if t["state"] == state]:
            t = min(todo, key=lambda t: min(np.hypot(*np.subtract(t["page"], p)) for p in page_hits))
            m, _, ruler = fit()
            publish(f"Calibrating: {sum(t['hit'] is not None for t in targets)} of {len(targets)} targets", ruler=ruler)
            aim(t, m, learn)
            if t["state"] == "miss" and state == "miss":
                t["state"] = "missed"
            if t["err_mm"] is not None:
                say(f"  target was {t['err_mm']:.1f} mm off, map corrected")
    landed = sum(t["hit"] is not None for t in targets)
    if landed < 4:
        publish(f"Only {landed} targets were touched")
        raise CalibError(f"Only {landed} target taps touched the screen, need 4 or more. Part of the phone "
                         "may be outside the work area, or the stylus does not reach the glass everywhere.")

    m, error_mm, ruler = fit()
    sx, sy = (float(np.hypot(*ruler[k])) / 10 for k in ("x", "y"))
    small, big = sorted(np.linalg.svd(m[:2, :2], compute_uv=False))
    if small < 0.95 * big:  # page pixels are square, so a mm must be the same size along X and along Y
        raise CalibError(f"The machine's X and Y do not fit a flat screen: {sx:.2f} page pixels per mm along X, "
                         f"{sy:.2f} along Y. Check the steps per mm, and that the phone lies flat.")
    say(f"Map fitted from {len(page_hits)} touches: {sx:.2f} page pixels per mm along X, {sy:.2f} along Y, "
        f"fit error {error_mm:.2f} mm")
    hom = m @ to_page  # image pixel -> page pixel -> mm
    corners = [apply_homography(hom, cx, cy) for cx, cy in ((0, 0), (w, 0), (w, h), (0, h))]
    xs, ys = zip(*corners)
    box = [round(float(v), 1) for v in (min(xs), min(ys), max(xs), max(ys))]

    # 4. Check round: every target once more with the final map, on a clean page
    view["round"] += 1
    for t in targets:
        t.update(state="todo", hit=None, err_mm=None)
    say("Checking the result...")

    def twice(x: float, y: float) -> Point | None:  # a tap may not register
        return try_tap(x, y) or try_tap(x, y)

    for i, t in enumerate(targets):
        publish(f"Check: {i} of {len(targets)}")
        aim(t, m, twice)
        if t["state"] == "miss":
            t["state"] = "missed"

    def to_image(p: Point | None) -> list[float] | None:
        return [float(v) for v in apply_homography(to_img, *p)] if p else None

    check = {"size": [w, h], "ok_mm": cfg.ok_mm, "px_per_mm": [round(sx, 3), round(sy, 3)],
             "targets": [{"px": to_image(t["page"]), "dot": to_image(t["hit"]), "err_mm": t["err_mm"],
                          "state": t["state"]} for t in targets]}
    publish(check_summary(check))
    return Calibration(hom, error_mm=error_mm, screen_box=box, check=check)


def check_summary(check: dict) -> str:
    """One line about the check round, e.g. "Check: 9 of 9 dots on target, worst 0.8 mm"."""
    errs = [t["err_mm"] for t in check["targets"] if t["err_mm"] is not None]
    good = sum(e <= check["ok_mm"] for e in errs)
    text = f"Check: {good} of {len(check['targets'])} dots on target"
    return text + (f", worst {max(errs):.1f} mm" if errs else "")


def box_center(box: list[float] | None) -> Point | None:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) if box else None
