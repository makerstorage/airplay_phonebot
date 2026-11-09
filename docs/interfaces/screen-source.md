# ScreenSource interface — `airplay`

Box 4 of the diagram. Gives the Session (and, read-only, the actuator) frames of the phone's screen in screen
space.

```python
class ScreenSource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def latest_frame(self) -> Frame | None: ...
    async def fresh(self, after_seq: int, timeout: float) -> Frame | None: ...  # first frame newer than after_seq
    async def settled(self, quiet: float, most: float) -> Frame | None: ...    # screen stopped changing
    async def calibrate(self) -> bool: ...
    def health(self) -> Health: ...
```

```python
@dataclass(frozen=True)
class Health:
    state: str      # ok | stale | down
    reason: str     # human readable, e.g. "no phone mirroring to GhostHand"
```

The Observer given to the actuator is the same object without `start`, `stop`, `calibrate`.

## GhostHand implementation

Two processes on the Pi, so restarting the server keeps the phone's mirroring session:

| Process | Does |
|---|---|
| `python -m hidagent.receiver` | runs UxPlay (restarts it if it exits), cuts its output into JPEGs, serves them on `127.0.0.1:8891` (`MIRROR_PORT`) |
| server (`Screen(stream="127.0.0.1:8891")`) | follows that stream and keeps the latest frame |

Stream on 8891: raw concatenated JPEGs (`FFD8 … FFD9`), no framing. On connect the current frame is sent at once,
then each new one. The socket closing means the phone went away.

| Method | Today in `screen.py` |
|---|---|
| `start()` / `stop()` | `Screen.start()` / `Screen.stop()`; `restart()` restarts a frozen UxPlay |
| `latest_frame()` | `Screen.frame` (bytes) + `Screen.updated` (time) |
| `fresh()` | `Screen.fresh(since: float, timeout)` — by time, not seq |
| `settled()` | `Screen.settled(quiet, least, most)` — returns nothing, read `frame` after |
| `calibrate()` | nothing to do: AirPlay frames are exact. Returns `True` |
| `health()` | `Screen.live`: `down` if UxPlay is not running or has no established TCP client (read from `/proc`) |

Things the Session must know about this source:

- AirPlay sends frames **only when the screen changes**. A still screen is not a frozen one. To tell them apart
  the actuator nudges the pointer and waits for a frame (`Phone.ensure_live`).
- Rate: about 8 fps, JPEG quality 75.
- When UxPlay restarts (`pi.sh start`) the user has to choose Control Center → Screen Mirroring → GhostHand
  again. `health()` reports `down` with that reason.
- Orientation follows the phone: a landscape iPad gives a landscape frame.
