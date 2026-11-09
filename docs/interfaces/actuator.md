# Actuator interface — `ble-mouse`

Box 5 of the diagram. Takes gestures in screen fractions and performs them on the phone.

```python
class Actuator(Protocol):
    capabilities: Capabilities
    def attach(self, observer: Observer) -> None: ...   # read-only frames, for aiming
    async def execute(self, gesture: Gesture) -> None: ...
    async def home(self) -> None: ...
    async def stop(self) -> None: ...                  # release everything, abort the current gesture
    async def calibrate(self) -> bool: ...
    def calibrated(self) -> bool: ...
    def health(self) -> Health: ...
```

```python
@dataclass(frozen=True)
class Capabilities:
    pointer: str            # "relative" for a mouse
    gestures: set[str]      # gesture types execute() accepts
    keys: set[str]          # keys key() can send
    text: bool              # can type text directly
    needs_observer: bool    # needs to see the screen
    typical_error: float    # miss after calibration, screen fraction
```

GhostHand `ble-mouse` capabilities:

```python
Capabilities(pointer="relative",
             gestures={"tap", "swipe", "drag", "scroll", "type", "key", "home", "release_all"},
             keys={"enter", "tab", "esc", "backspace", "cmd+<letter>", ...},  # see BleDevice._combo
             text=True,            # ASCII; other text goes through the clipboard
             needs_observer=True,
             typical_error=0.004)  # iPad: 1.5 pt average, 5 pt worst, with aiming
```

Rules for every actuator: a gesture is atomic and always ends with nothing pressed, even on error. `stop()`
must work while a gesture runs.

## GhostHand implementation

Two layers inside the actuator:

| Part | File | Speaks |
|---|---|---|
| pointer logic | `phone.py` (`Phone`) | screen fractions in, protocol lines out; calibration, aiming, liveness |
| HID link | `ble.py` (`BleDevice`) | protocol lines in, BLE HID reports out (mouse, keyboard, consumer Home) |

The line protocol between them (also used by the ESP32 `tcp` board, and by `POST /api/raw` in debug):

| Line | Effect |
|---|---|
| `move dx dy` | relative move in mouse units |
| `click` / `press` / `release` | left button |
| `scroll v h` | wheel |
| `type <text>` | HID keyboard, ASCII |
| `key <combo>` | e.g. `enter`, `cmd+r` |
| `homescreen` | Consumer AC Home (go home) |
| `home` | push pointer to the top-left corner — **not on iPad** (opens Notification Center) |
| `release_all` | all buttons and keys up |
| `ping`, `stats`, `tune step step_ms` | diagnostics |

Each line answers `ok` or `err <reason>`, e.g. `err ble not connected`.

| Method | Today |
|---|---|
| `execute(gesture)` | `Phone.tap / swipe / drag / scroll / type / key` (see [frame-and-gesture.md](frame-and-gesture.md)) |
| `home()` | `Phone.go_home()` → `homescreen` when `POINTER_HOME=find` |
| `stop()` | `release_all` line (no abort of a running move yet) |
| `calibrate()` | `Phone.start_calibration()`; in find mode it fits from two pointer sightings |
| `calibrated()` | `Phone.calibrated` |
| `health()` | `BleDevice.connected` + `Phone.calibrated`; `Phone.ensure_live()` raises `PhoneUnavailable` |

Notes:

- `POINTER_HOME=find` (set by `pi.sh`): the pointer is found on the frame instead of homed to a corner, and
  moves stay 1 % away from the edges. Needed on iPad.
- `limits.precise=True` aims: move, find the pointer on the frame, correct, then click. About 1 s slower; without
  it taps drift by about 25 pt on the iPad.
- Calibration is stored in `~/.hidagent/calibration.json` per device. Find-calibration reads the span about 6 %
  too big on the iPad, so the current span was set from tap-test data; don't recalibrate without checking.
- The phone has to be paired with **GhostHand** and AssistiveTouch on (iPhone) for the pointer to show.
