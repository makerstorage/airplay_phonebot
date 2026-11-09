# Frame and Gesture

The two data types from the diagram. They are the only things that pass between the Screen Source, the
Session and the Actuator.

## Frame (Screen Source → Session, Observer)

```python
@dataclass(frozen=True)
class Frame:
    image: bytes        # JPEG, already in screen space
    width: int          # pixels of image
    height: int
    seq: int            # goes up with every new frame
    timestamp: float    # time.time() it arrived
    transform: Transform
```

```python
@dataclass(frozen=True)
class Transform:
    orientation: str    # portrait | landscape_left | landscape_right
    crop: tuple[float, float, float, float] = (0, 0, 1, 1)  # part of the raw image that is the screen
    homography: list[list[float]] | None = None            # camera sources only
    fidelity: str = "exact"                                # exact (AirPlay, USB) | optical (camera)
```

GhostHand `airplay`: the AirPlay picture is the screen itself, so `crop` is the full image, `homography` is
`None` and `fidelity` is `exact`. The iPad in portrait gives 810 × 1080 (aspect 0.75).

Today `Screen` keeps `frame` (bytes) and `updated` (timestamp) as separate attributes; `seq`, size and
`transform` are not stored yet.

## Gesture (Session → Actuator)

```python
@dataclass(frozen=True)
class Gesture:
    type: str                        # see table
    points_norm: list[tuple[float, float]] = ()  # screen fractions 0..1
    text: str | None = None          # for type
    key: str | None = None           # for key, e.g. "enter", "cmd+r"
    lines: int = 0                   # for scroll: + up, - down
    limits: Limits = Limits()
```

```python
@dataclass(frozen=True)
class Limits:
    precise: bool = False            # aim: find the pointer and correct before pressing
    hold: float = 0.0                # seconds to keep pressed (long press)
    hold_end: bool = True            # swipe: stay at the end before lifting
    tolerance: float | None = None   # close enough, screen fraction
    timeout: float = 10.0            # give up after this many seconds
```

| type | points_norm | other fields | GhostHand `ble-mouse` does |
|---|---|---|---|
| `tap` | 1 | `precise`, `hold` | `Phone.tap` → `move`, `click` |
| `double_tap` | 1 | | two taps (not implemented yet) |
| `long_press` | 1 | `hold` | `press`, wait, `release` (not implemented yet) |
| `swipe` | 2 | `hold_end` | `Phone.swipe` |
| `drag` | 2+ | `hold_end` | `Phone.drag` |
| `scroll` | 1 (where) | `lines` | `Phone.scroll` → `scroll` |
| `type` | 0 | `text` | `Phone.type` → HID keyboard |
| `key` | 0 | `key` | `Phone.key` → HID keyboard |
| `home` | 0 | | `homescreen` (Consumer AC Home) |
| `release_all` | 0 | | `release_all` |

`back` and `app_switcher` are not gestures: the Session turns them into a `swipe` from the device profile.
