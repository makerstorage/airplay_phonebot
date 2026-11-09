"""Types that cross layer boundaries (docs/architecture.md, docs/interfaces/frame-and-gesture.md).

Every coordinate is a screen fraction 0.0-1.0 of the visible screen, origin top-left.
"""

from dataclasses import asdict, dataclass, field

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # x0, y0, x1, y1

# Gesture types and how many points each takes (None = any number >= 2)
GESTURE_POINTS: dict[str, int | None] = {
    "tap": 1,
    "double_tap": 1,
    "long_press": 1,
    "swipe": 2,
    "drag": None,
    "scroll": 1,
    "type": 0,
    "key": 0,
    "home": 0,
    "back": 0,
    "release_all": 0,
    # Open-ended touch, used by the agent's left_mouse_down / mouse_move / left_mouse_up
    "touch_down": 1,
    "touch_move": 1,
    "touch_up": 0,
}


@dataclass(frozen=True)
class Limits:
    precise: bool = False          # aim before pressing (pointer actuators)
    hold: float = 0.0              # seconds to keep pressed (long press)
    hold_end: bool = True          # swipe/drag: stay at the end before lifting
    tolerance: float | None = None # close enough, screen fraction
    timeout: float = 10.0          # give up after this many seconds


@dataclass(frozen=True)
class Gesture:
    type: str
    points_norm: tuple[Point, ...] = ()
    text: str | None = None        # for type
    key: str | None = None         # for key, e.g. "enter", "cmd+r"
    lines: int = 0                 # for scroll: + up, - down
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self):
        if self.type not in GESTURE_POINTS:
            raise ValueError(f"unknown gesture type '{self.type}'")
        n = GESTURE_POINTS[self.type]
        pts = self.points_norm
        if (n is None and len(pts) < 2) or (n is not None and len(pts) != n):
            raise ValueError(f"'{self.type}' needs {n if n is not None else '2 or more'} points, got {len(pts)}")
        for x, y in pts:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(f"point ({x}, {y}) is outside the screen (0..1)")
        if self.type == "type" and not self.text:
            raise ValueError("'type' needs text")
        if self.type == "key" and not self.key:
            raise ValueError("'key' needs key")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["points_norm"] = [list(p) for p in self.points_norm]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Gesture":
        limits = Limits(**(d.get("limits") or {}))
        return cls(
            type=d["type"],
            points_norm=tuple((float(x), float(y)) for x, y in d.get("points_norm") or ()),
            text=d.get("text"),
            key=d.get("key"),
            lines=int(d.get("lines") or 0),
            limits=limits,
        )


@dataclass(frozen=True)
class ActResult:
    ok: bool
    error: str | None = None       # not_calibrated | screen_unavailable | device_unavailable | busy | unsupported
                                   # | skipped | failed | timeout | stopped
    started: float = 0.0           # time.time() the gesture was sent
    finished: float = 0.0
    note: str | None = None        # human actuator: what the person typed when answering


@dataclass(frozen=True)
class Health:
    state: str                     # ok | stale | down
    reason: str = ""


@dataclass(frozen=True)
class Capabilities:
    pointer: str                   # absolute | relative
    gestures: frozenset[str]
    keys: frozenset[str]
    text: bool
    needs_observer: bool
    typical_error: float           # screen fraction
