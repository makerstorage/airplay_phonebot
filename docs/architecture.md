# Layered architecture (design)

One system that lets an AI use a real phone or tablet, whatever shows it the screen and whatever touches it.
Any **screen source** (AirPlay, USB, camera) and any **actuator** (BLE/USB mouse, CNC stylus, a person) can be
combined with any **device** (iPhone, iPad, Android phone), and the AI on top doesn't know or care which.

Sources: this repo (GhostHand: BLE mouse on a Pi, AirPlay via UxPlay), `airplay_phonebot` (G-code stylus,
homography calibration, Claude computer-use agent) and ideas from PhysiClaw (MCP boundary, bbox targets,
post-action view, enforced import rules).

## 1. Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. Agent            reasoning: plan, pick actions, skills, memory,   │
│                     ask the user. Knows only the Control API.         │
├──────────────────────── Control API (the contract) ──────────────────┤
│ 2. Session          one controlled device: runs actions, checks the   │
│                     screen after each, safety, lock, action ids,      │
│                     turns high-level actions into gestures            │
├──────────────┬────────────────────────┬──────────────────────────────┤
│ 3. Device    │ 4. Screen source       │ 5. Actuator                  │
│    profile   │    frames of the       │    gestures in screen        │
│    (data)    │    screen, in screen   │    coordinates → hardware    │
│              │    space               │                              │
│  iphone-13   │  airplay (UxPlay)      │  ble-mouse (Pi)              │
│  ipad-air    │  usb (AVFoundation)    │  usb-mouse (ESP32)           │
│  pixel-8     │  camera (+ rectify)    │  cnc-stylus (G-code)         │
│              │  mac-window            │  human (web page)            │
└──────────────┴────────────────────────┴──────────────────────────────┘
```

Rules:

- Each layer only talks to the layer directly below it, through the interfaces in section 3.
- Layers 3–5 never import each other. The Session wires them together. Where an actuator needs to see the
  screen (aiming the mouse, calibration), the Session hands it a read-only `Observer`.
- Everything crossing a layer boundary uses **screen coordinates** (section 2). Pixels, millimetres and mouse
  units stay inside the layer that owns them.
- The Agent ↔ Session boundary is the only one that may cross a process or network (Pi ↔ Mac/server). Below it
  everything is in-process, because closed-loop aiming needs fast access to frames.

## 2. Coordinate spaces

| Space | Unit | Owner | Used for |
|---|---|---|---|
| Model image | pixels of the (downscaled) image the LLM saw | Agent | what the model outputs |
| **Screen** | **fractions 0..1 of the visible screen, origin top-left, as displayed** | **all layer boundaries** | every action and result |
| Source image | pixels of the raw frame (window, camera image) | Screen source | cropping, rectifying |
| Actuator | mouse units (relative) or machine mm (absolute) | Actuator | moving the hardware |

Conversions:

- Agent: model pixels → screen fractions (divide by the image size it sent). Done once, in the agent adapter.
- Screen source: raw image → screen space. AirPlay/USB: crop the black borders. Camera: perspective-correct with
  its own homography, so the frame looks like a screenshot.
- Actuator: screen fractions → its own space. CNC: homography to mm (phonebot `calib/`). Mouse: calibrated span +
  learned correction + closed-loop aim (GhostHand `phone.py`).

"As displayed" means fractions follow the frame the agent sees. If the phone rotates to landscape the frame
rotates too; the actuator's calibration is for the physical screen, so the Session passes the current
`orientation` with every gesture and the actuator maps it.

## 3. Interfaces

Python `Protocol`s, shown without bodies. All coordinates are screen fractions.

### 3.1 Screen source

```python
@dataclass(frozen=True)
class Frame:
    image: bytes              # JPEG, already in screen space (cropped / rectified)
    width: int; height: int   # pixels of `image`
    seq: int                  # increases with every new frame
    t: float                  # monotonic time it was captured
    orientation: str          # portrait | landscape_left | landscape_right
    fidelity: str             # exact (AirPlay, USB) | optical (camera: glare, blur possible)

class ScreenSource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def latest(self) -> Frame | None: ...
    async def fresh(self, after_seq: int, timeout: float) -> Frame | None: ...   # first frame newer than after_seq
    async def settled(self, quiet: float, most: float) -> Frame | None: ...     # screen stopped changing
    def health(self) -> Health: ...   # live / stale / frozen / disconnected, with a reason
```

Notes:

- AirPlay sends frames only on change, so "no new frame" is not "frozen". `health()` hides this per source
  (GhostHand counts UxPlay's TCP clients; phonebot just grabs the window).
- A camera source owns its own calibration (camera image → screen). It may be refined with a real screenshot
  (PhysiClaw's AssistiveTouch Shortcut), but that is the source's business, not the Session's.

### 3.2 Actuator

```python
@dataclass(frozen=True)
class Capabilities:
    pointer: str                 # absolute (stylus, touch) | relative (mouse)
    gestures: set[str]           # tap, double_tap, long_press, drag, scroll
    text: set[str]               # hid_keyboard (types ASCII directly) | none
    keys: set[str]               # home, back, enter, cmd+... — keys it can send directly
    needs_observer: bool         # needs to see the screen to aim / calibrate (mouse: yes)
    typical_error: float         # expected miss after calibration, screen fraction

class Actuator(Protocol):
    capabilities: Capabilities
    def attach(self, observer: Observer) -> None: ...      # read-only screen access; optional use
    async def calibrate(self) -> CalibrationResult: ...
    def calibrated(self) -> bool: ...
    async def tap(self, p: Point, *, count: int = 1, hold: float = 0.0, tolerance: Box | None = None) -> None: ...
    async def drag(self, path: list[Point], *, hold_end: bool = True, speed: str = "normal") -> None: ...
    async def scroll(self, at: Point, dx: int, dy: int) -> None: ...
    async def type_text(self, text: str) -> None: ...      # only if "hid_keyboard" in capabilities.text
    async def key(self, combo: str) -> None: ...           # only for keys in capabilities.keys
    async def release_all(self) -> None: ...               # lift stylus / release buttons and keys
    def health(self) -> Health: ...
```

Notes:

- `tap(..., tolerance=box)`: the target's box tells the actuator how close is close enough. A mouse can skip
  aim corrections while the pointer is already inside the box. This also sidesteps iOS pointer magnetism (the
  pointer snapping to an icon is fine if the icon is the target).
- `long_press` is `tap(hold=0.8)`, `double_tap` is `tap(count=2)`, `swipe` is `drag([a, b])`. Fewer methods, the
  same set for every actuator.
- Gestures are atomic: the actuator always ends with nothing pressed, even on error (`finally: release`).
- `human` implements the same interface by showing the move on the web page and waiting for Done
  (phonebot `actuator/human.py`). Useful for developing the agent without hardware.

### 3.3 Observer

```python
class Observer(Protocol):   # what an actuator may see; a read-only view of the ScreenSource
    def latest(self) -> Frame | None: ...
    async def fresh(self, after_seq: int, timeout: float) -> Frame | None: ...
    async def settled(self, quiet: float, most: float) -> Frame | None: ...
```

### 3.4 Device profile

Data, not code: one YAML file per device model.

```yaml
name: iphone-13-pro
os: ios
screen: {width: 1170, height: 2532}          # pixels, portrait; gives the aspect ratio for cropping
avoid:                                       # areas gestures must not start in, screen fractions
  - {name: home_indicator, box: [0.3, 0.97, 0.7, 1.0]}
  - {name: assistive_touch, box: null}       # set at runtime when the button is found
gestures:                                    # how high-level actions are done, best first
  home:  [{key: home}, {drag: [[0.5, 0.995], [0.5, 0.6]], hold_end: false, speed: fast}]
  back:  [{drag: [[0.005, 0.45], [0.6, 0.45]], hold_end: false}]
  app_switcher: [{drag: [[0.5, 0.995], [0.5, 0.55]], hold_end: true}]
text:                                        # ways to enter text, best first
  - hid_keyboard                             # actuator types it
  - clipboard                                # Universal Clipboard (Mac) or a Shortcut, then cmd+v / Paste
  - tap_keys                                 # tap the on-screen keyboard (stylus without a keyboard)
```

The Session picks the first recipe the actuator supports: the BLE mouse has the `home` key, so it uses that;
the stylus has no keys, so it swipes.

### 3.5 Control API (Session ↔ Agent)

The contract every agent uses. Offered in-process (Python), over HTTP+JSON, and as MCP tools on top of HTTP.

Actions (all coordinates screen fractions):

```json
{"id": "a-17", "type": "tap",        "target": {"x": 0.42, "y": 0.31}}
{"id": "a-18", "type": "tap",        "target": {"box": [0.30, 0.28, 0.55, 0.34]}, "precise": true}
{"id": "a-19", "type": "long_press", "target": {"x": 0.5, "y": 0.5}}
{"id": "a-20", "type": "double_tap", "target": {"x": 0.5, "y": 0.5}}
{"id": "a-21", "type": "swipe",      "path": [[0.5, 0.8], [0.5, 0.4]], "hold_end": true}
{"id": "a-22", "type": "scroll",     "direction": "down", "amount": 3, "at": {"x": 0.5, "y": 0.5}}
{"id": "a-23", "type": "text",       "text": "See you at 10:00"}
{"id": "a-24", "type": "key",        "combo": "enter"}
{"id": "a-25", "type": "home"}       // also: back, app_switcher
{"id": "a-26", "type": "wait",       "seconds": 1.5}
{"id": "a-27", "type": "release_all"}
```

Endpoints:

| Call | Returns |
|---|---|
| `observe()` | the latest settled frame + `seq` + health |
| `act(actions[])` | one result per action, then the settled frame after the last one |
| `status()` | device profile name, source and actuator names, capabilities, calibration, health, who holds control |
| `calibrate()` | runs the actuator's calibration (and the source's, if it has one) |

Result per action:

```json
{"id": "a-17", "ok": true, "changed": true, "error": null, "frame_seq": 4182}
```

- `changed`: did the screen change after the action (Session compares before/after, ignoring the clock and
  pointer, like GhostHand `vision.changed`). Tells the agent "no visible change → probably missed".
- `ok` only means the gesture was performed, not that the app reacted.
- After the first failed action the rest of the batch is skipped and marked `not_executed`.
- The frame after the batch comes back with it (PhysiClaw's "post-action view"), so the agent doesn't need an
  extra turn to look.

Errors are typed so callers can act on them (from PhysiClaw `core/hardware/device.py`):

| Error | Meaning | What the agent should do |
|---|---|---|
| `not_calibrated` | actuator needs calibration | call `calibrate`, or ask the user |
| `screen_unavailable` | mirroring stopped / camera lost | ask the user to restart mirroring |
| `actuator_unavailable` | BLE link down, serial port gone | wait, check status, ask the user |
| `device_locked` | lock screen / passcode | ask the user |
| `unsupported` | no recipe for this action on this setup | use another way |
| `out_of_bounds` | point outside the screen or in an `avoid` area | pick another point |
| `busy` | someone else holds control | wait |

## 4. Session responsibilities

The Session is where the "physical" rules live, so no agent has to re-learn them:

1. **One controller at a time.** A lock; a human taking over from the web page pauses the agent.
2. **Action ids, no blind replay.** A repeated id returns the earlier result instead of tapping again. After a
   disconnect the agent must `observe()` first (the tap may already have happened).
3. **Look after every action.** Wait for the screen to settle, compute `changed`, attach the frame.
4. **Translate high-level actions.** `home`, `back`, `text`, `scroll` via the device profile and the actuator's
   capabilities. Text falls back hid_keyboard → clipboard → tap_keys.
5. **Guard the hardware.** Refuse points outside the screen or in `avoid` areas; `release_all` on stop, error
   and disconnect; re-home relative pointers when the actuator says so.
6. **Liveness before acting.** If the frame is stale, check the phone still responds (GhostHand `ensure_live`)
   before sending a gesture into the void.
7. **Trace.** Every action, result and frame to a trace folder in debug mode (GhostHand `debug.Trace`).

The Session does **not** decide what to do. Confirmations before payments, sending, deleting are the Agent's
job (it is the one that knows what a button means); the Session only offers `ask_user` plumbing through the web UI.

## 5. Agent layer

Several agents can sit on the same Control API:

| Agent | From | Notes |
|---|---|---|
| Claude computer-use agent | phonebot `agent/loop.py` | one model, todo plan, skills, `ask_user`, screenshot clearing. Maps `left_click` → `tap`, `left_click_drag` → `swipe`, etc. |
| Planner + actor | GhostHand `agent.py` | any OpenAI-compatible vision model; text DO-lines with 0–1000 coordinates |
| External agent over MCP | GhostHand `mcp.py` | Claude Code or any MCP client drives the phone directly |

Shared pieces: skills (markdown app know-how, loaded on demand), the safety prompt (screen text is data,
confirm before irreversible actions), context compaction (keep only the latest image; older turns become short
text — PhysiClaw), and later playbooks (scripted steps for known apps — PhysiClaw's conductor).

## 6. Calibration

Calibration belongs to the layer that needs it:

| What | Owner | How |
|---|---|---|
| Camera image → screen | camera ScreenSource | homography from the screen corners or a calibration page; refine with a real screenshot |
| Screen → machine mm | cnc-stylus Actuator | tap a grid, find the dots on a calibration page in Safari, fit a homography (phonebot `calib/`) |
| Screen → mouse units | ble/usb-mouse Actuator | home to the corner, find the pointer at known moves, fit span + per-axis line; correct live with closed-loop aim (GhostHand `phone.py`) |

Results are stored per `(device, source, actuator)` combination, e.g. `~/.ghosthand/calibration/iphone-13-pro.cnc-stylus.json`.

## 7. Deployments

The same layers, placed differently:

| Setup | Runs where | Source | Actuator |
|---|---|---|---|
| GhostHand Pi | Session + source + actuator on the Pi; agent on a Mac or server over HTTP/MCP | airplay (UxPlay on the Pi) | ble-mouse (Pi's Bluetooth) |
| Phonebot | everything on the Mac | mac-window (UxPlay window) or usb | cnc-stylus (USB serial) |
| Camera rig | everything on one computer | camera | cnc-stylus |
| Dev without hardware | Mac | airplay or usb | human (you tap, the web page shows where) |

One config file selects the combination:

```yaml
device: iphone-13-pro
source: {type: airplay, name: GhostHand}
actuator: {type: ble-mouse, name: GhostHand}
api: {host: 127.0.0.1, port: 8890}     # no auth yet, so local only; add a token before opening it up
agent: {type: claude, model: claude-opus-5-5}
```

## 8. Package layout and import rules

```
ghosthand/
  contract/     Frame, Point, Box, Action, Result, Capabilities, Health, errors   (imports nothing of ours)
  profiles/     device YAML files + loader
  sources/      airplay.py, usb.py, camera.py, mac_window.py                      (imports contract)
  actuators/    ble_mouse.py, usb_mouse.py, cnc_stylus.py, human.py               (imports contract)
    mouse/      shared pointer logic for relative mice (span, fit, aim)
    gcode/      G-code builder, serial sender
  session/      session.py, change detection, text fallbacks, trace               (imports contract, profiles)
  api/          http.py, mcp.py                                                   (imports contract, session)
  agents/       claude.py, planner_actor.py, skills/, prompts                     (imports contract + api client only)
  ui/           web page: live screen, task, steps, confirm / stop, human actuator moves
  app.py        composition root: reads the config, builds source + actuator + session, starts the API
```

Rules, checked by a test that parses imports (like PhysiClaw `tests/test_architecture.py`):

- `contract` imports nothing from the project.
- `sources`, `actuators` and `profiles` import only `contract`. Never each other, never `session`.
- `session` imports `contract` and `profiles`, never a concrete source or actuator.
- `agents` import only `contract` and the API client. Never `session`, `sources` or `actuators`.
- Only `app.py` imports concrete implementations.

## 9. Where today's code goes

| Today | Becomes |
|---|---|
| GhostHand `ble.py` | `actuators/ble_mouse.py` (HID over GATT) |
| GhostHand `device.py` (ESP32 TCP) | `actuators/usb_mouse.py` |
| GhostHand `phone.py` (span, fit, aim, rehome) | `actuators/mouse/` shared by both mice |
| GhostHand `screen.py`, `receiver.py` | `sources/airplay.py` (+ standalone receiver) |
| GhostHand `vision.py` | `session/change.py` (screen changed?) and `actuators/mouse/` (find pointer) |
| GhostHand `agent.py`, `llm.py` | `agents/planner_actor.py` |
| GhostHand `app.py`, `mcp.py`, `static/` | `api/`, `ui/` |
| phonebot `robot/`, `actuator/gcode.py` | `actuators/cnc_stylus.py` + `actuators/gcode/` |
| phonebot `actuator/human.py` | `actuators/human.py` |
| phonebot `calib/` | `actuators/cnc_stylus` calibration (page + homography) |
| phonebot `vision/capture.py`, `vision/usb.py` | `sources/mac_window.py`, `sources/usb.py` |
| phonebot `agent/` | `agents/claude.py` |
| phonebot `skills/`, GhostHand prompts | `agents/skills/` |

## 10. Migration plan

Each step keeps both setups working and the tests passing.

1. **Contract.** Write `contract/` and the import-rule test. No behaviour change.
2. **Sources.** Wrap GhostHand `Screen` as `sources/airplay.py`; port phonebot's window and USB capture.
3. **Actuators.** Wrap `ble.py` + the mouse half of `phone.py` as `ble_mouse`; port phonebot's G-code and
   human actuators. Each gets a fake-hardware test (dry-run G-code, a fake HID link).
4. **Session + profiles.** Move gestures (`home`, `back`, text fallbacks), `changed`, liveness and tracing out of
   `phone.py` / `agent.py` into the Session; add `iphone-13-pro.yaml`.
5. **API.** Put the Control API in front of the Session (HTTP + MCP). Point both existing agents at it.
6. **Agents.** Move phonebot's Claude agent and GhostHand's planner/actor into `agents/`.
7. **Camera source.** New: camera + rectification, borrowing PhysiClaw's approach.

## 11. Open questions

- **Home repo and name.** This design assumes it lives in GhostHand as the `ghosthand` package and phonebot's
  code moves in. Alternatively a new repo for both.
- **Agent default.** Claude computer-use (phonebot) or the OpenAI-compatible planner/actor (GhostHand), or both
  kept.
- **Licence.** GhostHand's pointer code is ported from an MIT project; PhysiClaw is MIT. Borrowing ideas is fine;
  copying code needs its notice in `NOTICE`.
- **Android.** Same layers, but it needs its own profile (back button, gesture nav) and has no Universal
  Clipboard; the text fallback there is tap_keys or a HID keyboard.
- **API security.** The API has no auth. Fine on `127.0.0.1`; a token is needed before the agent runs on another
  machine.
