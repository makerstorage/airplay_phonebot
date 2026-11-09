# Human Actuator Teaching UI — Spec

2026-11-09 · Nuri Erginer

## 1. Purpose

The Teaching UI lets a person show the AI how to use an app it does not know, then turns that demonstration into
a Markdown skill the agent loads whenever a task involves that app.

- The person performs a task on the real device while the UI records every gesture, the screen before and after
  it, and the person's notes.
- The AI turns one or more recordings into a skill: what the app's screens look like, where things are, the steps
  for the task, and the pitfalls.
- The agent never replays the recording. It reads the skill and still decides each action itself, so the skill
  keeps working when the screen differs a little.

## 2. Scope and place in the architecture

The Teaching UI is a client of the Control API, the same contract the Agent Runtime (box 1) uses. It never talks
to a Screen Source or an Actuator directly, so any source and actuator pair works behind it. GhostHand (AirPlay +
BLE mouse on the Pi) is the first backend. The `human` actuator (section 4.7) also lives in this repo.

| Part | Owned by | Notes |
| --- | --- | --- |
| Web page, recorder, recording store, skill writer | **this repo** | runs on the operator's Mac |
| Control API adapter for GhostHand | **this repo** | maps the contract onto GhostHand `:8890` until a real Session Manager exists |
| Actuator `human` (box 5) | **this repo** | the person is the actuator; the web page is its display (4.7) |
| Screen Source `airplay`, Actuator `ble-mouse` | GhostHand | on the Pi, reached over an SSH tunnel |
| Session Manager (box 2) | not built yet | the adapter stands in for it |
| Agent Runtime (box 1) | agent repo | loads the skills this repo writes |

Two teaching modes. They differ only in which actuator sits behind the Control API; the page, the input
mapping and the recording are the same.

| Mode | Actuator | Who touches the device | How gestures are known |
| --- | --- | --- | --- |
| **Drive** | `ble-mouse` (GhostHand) | the BLE mouse, driven by the person's clicks on the streamed image | exact: the UI builds each Gesture |
| **Watch** | `human` (4.7) | the person, by hand | exact for moves entered on the image first; inferred for free touches |

Out of scope: the agent loop, replaying recordings, other devices' calibration, and multi-user access.

```
 Teaching UI page (browser)
        │ 4.3 teaching server API
 Teaching server (Mac) ── recorder ── recordings/ ── skill writer ── skills/
        │ 4.1 ControlClient
        ├── frames ◄──────── GhostHand Screen Source `airplay` (Pi)
        └── act(gesture) ──► Drive: GhostHand Actuator `ble-mouse` (Pi) ──► device
                             Watch: Actuator `human` (Mac) ──► page shows the move ──► person ──► device
```

## 3. User flow

One teaching session records one task in one app, from the goal to the outcome.

1. **Start.** The person opens the page, picks the app (name + bundle id, new or existing), types the task goal
   (e.g. "export last month's report as PDF"), and picks the mode: Drive or Watch.
2. **Perform.** The live screen shows in the page. In both modes the person enters each move on the image
   (4.2).
    - Drive: the move is sent as one Gesture to the BLE mouse, which performs it. The page draws the gesture on
      the frame as it goes.
    - Watch: the move goes to the `human` actuator. The page shows it as a prompt ("Tap here", with the target
      drawn on the frame), the person does it on the device by hand and presses Done. A touch done without
      entering it first is still recorded as an inferred step.
3. **Annotate, at any time.** The person can type a note on the current step ("open the export menu"), or draw a
   box on the frame and name the element ("Export button"). Notes and marks attach to the latest step.
4. **Finish.** The person presses Finish, marks the outcome (success / failed / partial) and can add a closing
   note. The recording is saved.
5. **Write the skill.** The person presses Write skill. The skill writer reads the recording and the app's current
   SKILL.md, if there is one, and drafts the new version.
6. **Review.** The page shows the draft as a diff against the current skill, with the chosen screenshots. The
   person edits and approves; only then is it written to the skill store.

Stop is always one click away: it calls the actuator's `stop()` (`release_all` on the BLE mouse, cancel the open
prompt on `human`) and pauses the recording.

## 4. Interface definitions

Six interfaces cross this repo's edges: the Control API it calls, the browser API it serves, the recording it
writes, the skill it produces, the skill writer it calls, and the `human` actuator it implements. `Frame`,
`Gesture` and `Limits` are the architecture's types (GhostHand `docs/interfaces/frame-and-gesture.md`), used
unchanged. Every coordinate is a screen fraction 0.0–1.0, origin top-left.

### 4.1 Control API client (southbound)

The only way the Teaching UI reaches a device. It is the subset of the Control API contract that teaching needs.

```python
class ControlClient(Protocol):
    async def status(self) -> Status: ...                  # device, screen, calibrated, aspect, actuator
    async def latest_frame(self) -> Frame | None: ...
    def frames(self) -> AsyncIterator[Frame]: ...           # each new frame as it arrives
    async def act(self, gesture: Gesture) -> ActResult: ...
    async def stop(self) -> None: ...                       # release everything, abort the running gesture

@dataclass(frozen=True)
class Status:
    device: bool            # actuator linked (human: a page is open to show moves)
    screen: bool            # frames live
    calibrated: bool
    aspect: float           # width / height of the frame
    actuator: str           # "ble-mouse" | "human"

@dataclass(frozen=True)
class ActResult:
    ok: bool
    error: str | None       # not_calibrated | screen_unavailable | device_unavailable | busy | unsupported
                            # | skipped | failed | timeout | stopped   (the last four: human only)
    started: float          # time.time() the gesture was sent
    finished: float
    note: str | None = None # human only: what the person typed when answering the prompt
```

Implementations:

| Class | Frames from | `act()` goes to | Used by |
| --- | --- | --- | --- |
| `GhostHandClient` | GhostHand `/api/stream.mjpg` | GhostHand `/api/tap` etc. (`ble-mouse`) | Drive |
| `HumanClient` | GhostHand `/api/stream.mjpg` | `HumanActuator` in this process (4.7) | Watch |
| `FakeClient` | a folder of JPEGs | a log | tests |

`GhostHandClient`, over an SSH tunnel to the Pi's `127.0.0.1:8890`:

| ControlClient | GhostHand today | Gap to fill in GhostHand |
| --- | --- | --- |
| `status()` | `GET /api/status` | none |
| `latest_frame()` | `GET /api/frame.jpg` | no `seq` or size header yet |
| `frames()` | `GET /api/stream.mjpg` (MJPEG) | none |
| `act(tap)` | `POST /api/tap {x, y, precise}` | none |
| `act(swipe)` | `POST /api/swipe {x1, y1, x2, y2}` | none |
| `act(drag)` | none | add `POST /api/drag` (`Phone.drag` exists) |
| `act(long_press)` | none | add `POST /api/long_press {x, y, hold}` |
| `act(scroll)` | `POST /api/scroll {x, y, lines}` | none |
| `act(type)` / `act(key)` | `POST /api/type {text}` / `POST /api/key {text}` | none |
| `act(home)` / back | `POST /api/home` / `POST /api/back` | none |
| `stop()` | `POST /api/raw {"text":"release_all"}`, debug only | add `POST /api/stop` |

Errors: GhostHand answers HTTP 409 with text. The adapter maps that text onto the `error` codes above.

### 4.2 Browser input to Gesture (both modes)

The page turns pointer events on the image into Gestures. The image is drawn with its true aspect ratio, so
`x = offsetX / clientWidth` and `y = offsetY / clientHeight` give screen fractions.

| Input on the image | Gesture | Rule |
| --- | --- | --- |
| click | `tap`, `precise: true` | pointer moved < 1 % of the image between down and up, held < 500 ms |
| press and hold | `long_press`, `hold` = time held | moved < 1 %, held ≥ 500 ms |
| drag, released quickly | `swipe`, `hold_end: false` | moved ≥ 1 %; first and last point |
| drag, paused before release | `drag`, `hold_end: true` | moved ≥ 1 %, still ≥ 300 ms before up; points sampled every 50 ms |
| mouse wheel | `scroll` at the pointer | `lines` = wheel notches, + up, − down; notches within 250 ms are summed |
| typing while the image has focus | `type` | printable characters, sent after 400 ms with no keys |
| Enter, Tab, Esc, Backspace, Cmd+letter | `key` | sent at once |
| Home, Back buttons | `home` / back | back is a device-profile swipe, built by the Session |

One gesture runs at a time. Input that arrives while a gesture runs (or while a human prompt is open) is dropped,
and the page shows that it was.

### 4.3 Teaching server API (browser to server)

FastAPI on `127.0.0.1:8900` (configurable). JSON in and out, errors as `{"error": code, "detail": text}`.

| Call | Body | Returns |
| --- | --- | --- |
| `GET /api/status` | | the backend `Status` + the open session, if any |
| `GET /api/stream.mjpg` | | the live frames, passed through |
| `GET /api/apps` | | `[{app_id, name, bundle_id, skill: bool, recordings: n}]` |
| `POST /api/sessions` | `{app_id, app_name?, bundle_id?, goal, mode: "drive" \| "watch"}` | `{session_id}`; 409 if one is open |
| `POST /api/sessions/{id}/act` | a Gesture as JSON | `{step, ok, error?}`; both modes (Watch: returns when the person answers the prompt) |
| `POST /api/sessions/{id}/note` | `{text, step?}` | `{step}`; default = latest step |
| `POST /api/sessions/{id}/mark` | `{box: [x0, y0, x1, y1], label, step?}` | `{step}` |
| `POST /api/sessions/{id}/stop` | | `{ok}`; actuator `stop()`, recording paused |
| `POST /api/sessions/{id}/resume` | | `{ok}` |
| `POST /api/sessions/{id}/finish` | `{outcome: "success" \| "failed" \| "partial", note?}` | `{recording_path}` |
| `GET /api/sessions/{id}/events` | | Server-Sent Events: every recorder event as it is written (4.4) |
| `GET /api/human/prompts` | | Server-Sent Events: `prompt` and `cancel` events of the `human` actuator (4.7) |
| `POST /api/human/prompts/{prompt_id}` | `{result: "done" \| "skipped" \| "failed", note?}` | `{ok}`; 409 if already answered |
| `GET /api/recordings/{id}` | | `session.json` + events |
| `GET /api/recordings/{id}/frames/{seq}.jpg` | | one saved frame |
| `POST /api/recordings/{id}/skill` | `{writer?: "name"}` | `{draft_id}`; starts the skill writer |
| `GET /api/drafts/{draft_id}` | | `{status, skill_md, screens: [...], diff}` |
| `PUT /api/drafts/{draft_id}` | `{skill_md, screens}` | `{ok}`; the person's edits |
| `GET /api/drafts/{draft_id}/problems` | | `[{level: "error" \| "warning", check, detail}]` (4.6 validation) |
| `POST /api/drafts/{draft_id}/approve` | | `{skill_path}`; writes to the skill store; `409 invalid_skill` while errors remain |

### 4.4 Recording format

One folder per session, never edited after `finish`. A recording is a complete, offline input to the skill writer.

```
recordings/<app_id>/<YYYYMMDD-HHMMSS>-<short id>/
  session.json      # who, what, which device
  events.jsonl      # one event per line, in time order
  frames/<seq>.jpg  # every frame an event points at
```

```json
{
  "session_id": "20261109-142301-a7f3",
  "app": {"app_id": "acme-crm", "name": "Acme CRM", "bundle_id": "com.acme.crm", "version": "4.2.1"},
  "goal": "Export last month's report as PDF",
  "mode": "watch",
  "device": {"profile": "ipad", "os": "ipados", "aspect": 0.75, "orientation": "portrait"},
  "backend": {"client": "human", "screen_source": "airplay", "actuator": "human"},
  "started": 1762698181.2,
  "finished": 1762698422.9,
  "outcome": "success",
  "outcome_note": "PDF appeared in Files",
  "schema": 1
}
```

Event types in `events.jsonl` (every event has `t` = `time.time()` and `step`, the step it belongs to):

| `type` | Fields | Written when |
| --- | --- | --- |
| `frame` | `seq`, `path`, `width`, `height`, `role` | right before each gesture (`role: "before"`) and when the screen settles after it (`role: "after"`) |
| `gesture` | `gesture` (the full Gesture), `actor`: `ble-mouse` \| `human`, `ok`, `error?`, `note?`, `before_seq`, `after_seq` | after each `act()`; for `human` when the person answers the prompt |
| `step` | `before_seq`, `after_seq`, `inferred: true` | the screen settled after a change with no gesture running (Watch: a free touch). The gesture is unknown |
| `note` | `text` | the person types a note |
| `mark` | `box`, `label`, `seq` | the person names an element on a frame |
| `control` | `action`: `stop` \| `resume` \| `drop` | Stop pressed, or input dropped while busy |
| `outcome` | `outcome`, `note?` | Finish |

A step = one gesture, or one settled screen change with no gesture, with its before and after frame. "Settled"
uses the source's `settled()`: no new frame for 350 ms, at most 4 s.

### 4.5 Skill format

One folder per app, in the layout of Claude Agent Skills, so the agent loads it on demand.

```
skills/<app_id>/
  SKILL.md
  screens/<screen-name>.jpg     # key screens, with marked elements drawn on
  sources.json                  # which recordings built this version
```

```markdown
---
name: acme-crm
description: Operate the Acme CRM iPad app by screen: find customers, read and export reports. Use when a task mentions Acme CRM, its reports, or customer records. Triggers: Acme, CRM report, export report, customer record.
app:
  name: Acme CRM
  bundle_id: com.acme.crm
  versions_seen: ["4.2.1"]
  device_profiles: [ipad]
tasks: [export-report-pdf, find-customer]
updated: 2026-11-09
---

# Acme CRM

## Hard rules
- Never tap Send, Delete or Pay without the user's explicit "yes" for this task.
- Preview first: open the export sheet and check the date range before exporting.

## Screens
### Reports list  ![](screens/reports-list.jpg)
How to recognise it, what is where (positions as screen fractions), how to get here.

## Tasks
### export-report-pdf
Goal, numbered steps (screen, action, target element, what you should see after), how to tell it worked.

## Pitfalls
Things that went wrong or look misleading, and what to do instead.
```

Rules:

- **`description` decides when the skill loads.** The agent sees only `name` and `description` of every skill
  until one matches, so `description` says three things in at most 400 characters: what the skill does ("Operate
  the Acme CRM iPad app by screen"), when to use it ("Use when a task mentions …"), and a `Triggers:` list of the
  words a task would contain (app name, its jobs, its own terms). Pattern taken from the OpenClaw / Physiclaw
  skills (e.g. `food-order`).
- **Hard rules come first.** Any step that cannot be undone (send, delete, pay, submit, sign out, change settings)
  gets a rule in `## Hard rules`: what the agent must never do without the user's explicit yes, and what to
  check before it (preview, confirm the recipient or amount). The skill writer adds a rule for every such step it
  sees in a recording, even when the person did it without asking. The section is required; it may say "None
  found yet".
- **Concise.** Only what the agent cannot see or guess: where things are hidden, what a screen means, what goes
  wrong. No general advice on using an iPad. `SKILL.md` stays under 500 lines; more detail goes into
  `references/<topic>.md` files it links to.
- Positions are hints ("top right, about 0.92, 0.06"); the agent must still find the element on the live screen.
- Each task section lists the recordings it came from in `sources.json`, not in the text.

### 4.6 Skill writer

```python
class SkillWriter(Protocol):
    async def write(self, recording: Recording, current: Skill | None) -> SkillDraft: ...

@dataclass
class SkillDraft:
    skill_md: str                  # the whole new SKILL.md
    screens: list[ScreenShot]      # (name, frame seq, crop box, marks to draw)
    sources: list[str]             # recording ids
    diff: str                      # unified diff against current SKILL.md
```

The model is set in config, like GhostHand's `LLM_*` variables:

```yaml
skill_writer:
  provider: anthropic          # anthropic | openai-compatible
  base_url: null               # for openai-compatible, e.g. a local vLLM
  model: claude-opus-5-5
  api_key_env: ANTHROPIC_API_KEY
  max_frames: 60               # frames sent per recording; before/after of each step first
```

The writer's prompt includes the skill-writing guidance from `skill-creator` (Anthropic's, also in
[Physiclaw `skills/skill-creator`](https://github.com/CommanderZed/Physiclaw/tree/main/skills/skill-creator),
Apache-2.0): be concise, assume the agent is capable, and make a step only as specific as the task is fragile
(exact positions and checks for steps that break easily, plain goals for the rest).

**Validation.** Every draft is checked by `validate_skill(draft) -> list[Problem]` before the page shows it, and
again on Approve; Approve is refused (`409 invalid_skill`, with the problems) while any error remains. Based on
`skill-creator/scripts/quick_validate.py`, plus our own checks:

| Check | Level |
| --- | --- |
| front matter parses; `name` = folder name, lowercase letters, digits and hyphens, ≤ 64 characters | error |
| `description` present, ≤ 400 characters, contains "Use when" and `Triggers:` | error |
| `app.name` and `tasks` present; each id in `tasks` has a `### <id>` section | error |
| `## Hard rules`, `## Screens`, `## Tasks`, `## Pitfalls` present | error |
| every image link points at a file in `screens/`; every screen file is linked | error |
| every recording id in `sources.json` exists in `recordings/` | error |
| a step that sends, deletes, pays or submits has no matching hard rule | warning |
| `SKILL.md` over 500 lines | warning |
| inferred steps (4.4) still marked inferred | warning |

### 4.7 Human actuator

The `human` actuator is box 5 of the architecture with a person as the hardware (`architecture.md` §3.2,
phonebot `actuator/human.py`). It implements the same Actuator interface as `ble-mouse`: `execute(gesture)` shows
the move on the web page and returns when the person has done it on the device and pressed Done.

```python
class HumanActuator(Actuator):
    capabilities = Capabilities(
        pointer="absolute",           # a finger lands where it is told
        gestures={"tap", "double_tap", "long_press", "swipe", "drag", "scroll",
                  "type", "key", "home", "release_all"},
        keys={"home", "enter", "tab", "esc", "backspace", "cmd+<letter>"},  # shown as words, typed by the person
        text=True,                    # the person types it on the device keyboard
        needs_observer=False,
        typical_error=0.01,           # about 1 % of the screen: a finger aimed from a picture
    )

    def __init__(self, prompts: PromptChannel, timeout: float = 120.0): ...
    def attach(self, observer: Observer) -> None: ...   # unused
    async def execute(self, gesture: Gesture) -> None: ... # open a prompt, wait for the answer
    async def home(self) -> None: ...                    # execute(Gesture("home"))
    async def stop(self) -> None: ...                    # cancel the open prompt (result "stopped")
    async def calibrate(self) -> bool: ...               # nothing to calibrate: True
    def calibrated(self) -> bool: ...                    # True
    def health(self) -> Health: ...                      # ok while a page listens on /api/human/prompts
```

The prompt is the only data that crosses to the page:

```python
@dataclass(frozen=True)
class HumanPrompt:
    prompt_id: str
    gesture: Gesture              # drawn on the live frame: a ring for tap, an arrow for swipe/drag
    say: str                      # one line for the person, e.g. "Long-press here for 1 s"
    deadline: float               # time.time() after which it times out

@dataclass(frozen=True)
class HumanAnswer:
    prompt_id: str
    result: str                   # done | skipped | failed  (timeout, stopped: set by the actuator)
    note: str | None = None

class PromptChannel(Protocol):    # the teaching server implements it with SSE + POST (4.3)
    async def ask(self, prompt: HumanPrompt) -> HumanAnswer: ...
    def cancel(self, prompt_id: str) -> None: ...
    def listening(self) -> bool: ...
```

`say` per gesture type:

| Gesture | `say` |
| --- | --- |
| `tap` | Tap here |
| `double_tap` | Double-tap here |
| `long_press` | Long-press here for `hold` s |
| `swipe` / `drag` | Swipe along the arrow / Drag along the arrow and hold at the end |
| `scroll` | Scroll up / down `lines` lines here |
| `type` | Type: `text` |
| `key` | Press `key` |
| `home` | Go to the Home Screen |

Rules:

- One prompt is open at a time. `execute()` raises `busy` for a second one, like any actuator.
- Each prompt is answered once. Done → `ok`. Skipped, failed, timeout or stopped → `ActResult.ok = false` with
  that `error`, and the recorder keeps it as a pitfall candidate.
- The page shows the prompt over the live stream until it is answered, with Done (also the Space key), Skip and
  Failed buttons and an optional note.
- No page listening → `health()` is `down` with reason "no page open to show moves", and `act()` returns
  `device_unavailable` at once instead of waiting for the timeout.
- `typical_error` is larger than `ble-mouse` because nobody checks where the finger landed. The recorder keeps the
  entered point, not a measured one.

Two uses of the same actuator:

| Use | Who decides the move | Who answers the prompt |
| --- | --- | --- |
| Teaching, Watch mode | the person, by clicking on the image (4.2) | the same person, after doing it by hand |
| Agent development without hardware | the agent, through the Session | a person watching the page |

## 5. Coordinates and calibration

The Teaching UI does no calibration of its own: it sends screen fractions, and the actuator turns them into
pointer moves or prompts.

- The streamed image is the screen itself on AirPlay (`fidelity: exact`, full crop), so a click at fraction (x, y)
  on the image is (x, y) on the device.
- The page keeps the image at the frame's aspect ratio (`Status.aspect`) and recomputes on every new frame,
  because orientation can change mid-session.
- Drive mode sends taps with `precise: true`: GhostHand finds the pointer on the frame and corrects before
  clicking (about 1.5 pt average miss on iPad). Without it taps drift by about 25 pt.
- Before Start the page checks `Status.calibrated` and refuses Drive mode if it is false. The `human` actuator is
  always calibrated; Watch mode only needs the stream.
- Marks (4.4) are stored in the same fractions, so they line up with the gesture points and with screenshots of
  any size.

## 6. Skill generation

The skill writer turns a recording into a SKILL.md change that a person approves; nothing reaches the skill store
without review.

1. **Build the input.** For each step: the before and after frame, the gesture and its actor, and the notes and
   marks on that step. Plus the goal, the outcome and the app's current SKILL.md. Frames are capped at
   `max_frames`, keeping each step's before and after.
2. **Inferred steps first.** For `step` events with `inferred: true` (free touches in Watch mode), the model first
   says what most likely happened ("tapped Export at about 0.91, 0.07") from the frame change and the note. These
   guesses are marked as inferred in the draft. Steps done through the `human` actuator need no guess.
3. **Draft.** The model writes the whole new SKILL.md: new or updated screens, the task as numbered steps, and
   pitfalls (failed, skipped or timed-out gestures, dropped input, steps the person undid). It picks the key
   screens and their crops.
4. **Merge.** With an existing skill, the draft keeps every other task and screen and changes only what this
   recording shows. A conflict (the same step done two ways) is listed under Pitfalls with both ways, not
   overwritten.
5. **Validate.** The draft is checked (4.6 validation). Errors and warnings show next to the diff.
6. **Review.** The page shows the diff, screenshots and problems; the person edits, then approves. Approve
   validates again and, with no errors, writes `SKILL.md`, `screens/` and `sources.json`.

A failed or partial recording still feeds the skill, but only into Screens and Pitfalls, never as task steps.

## 7. Non-functional

| Topic | Decision |
| --- | --- |
| Where it runs | the operator's Mac, one user, `127.0.0.1` only, no auth |
| Reaching the Pi | SSH tunnel to GhostHand `127.0.0.1:8890`; GhostHand stays bound to localhost |
| Stack | Python 3.12+, FastAPI, uvicorn, httpx; one static page in plain JS, no build step (like `airplay_phonebot/web`) |
| Latency | stream: AirPlay ≈ 8 fps, about 100–300 ms behind; a precise tap ≈ 1 s; a human prompt waits up to 120 s; the page shows a busy state while a gesture runs |
| Storage | `recordings/` and `skills/` on disk, paths in config; skills can be a git repo the agent pulls |
| Privacy | recordings hold real screens; they stay on the Mac and are only sent to the configured skill-writer model |
| Tests | `FakeClient` (frames from a folder, gestures logged) and a scripted `PromptChannel` that answers prompts, so the page, recorder, human actuator and writer run without a device |

## 8. Decisions and open questions

Decided on 2026-11-09:

| Decision | Choice |
| --- | --- |
| Human's role | both modes: Drive (clicks on the image, BLE mouse acts) and Watch (the `human` actuator: the page prompts, the person acts by hand) |
| Human actuator | implements the architecture's Actuator interface (§3.2), lives in this repo, also usable by the agent without hardware |
| Backend | the Control API contract; GhostHand `:8890` through an adapter first |
| Recorded besides gestures and frames | typed step notes, task goal + outcome, named element marks |
| Output | a Markdown skill per app, loaded by the agent when a task involves that app |
| Gestures in v1 | tap, swipe, drag, scroll, long press, type, key, home, back |
| Watch capture | moves entered on the image are exact; free touches are recorded from frames + notes and inferred |
| Deployment | the operator's Mac, local only |
| Stack | FastAPI + plain JS |
| Skill store | `skills/<app_id>/SKILL.md` + `screens/`, merged across recordings, reviewed before save |
| Skill writer model | configurable: Anthropic or any OpenAI-compatible endpoint |
| Skill conventions | OpenClaw-style `description` with "Use when" + `Triggers:`; a required `## Hard rules` section for steps that cannot be undone; drafts validated before Approve |

Still open:

- [ ] Where the skills folder lives and how the agent gets it: a git repo it pulls, or a shared path.
- [ ] GhostHand additions for 4.1: `POST /api/drag`, `POST /api/long_press`, `POST /api/stop`, and `seq` on
      frames. Built in GhostHand or worked around in the adapter?
- [ ] How the app is identified when the person does not know the bundle id: typed name only, or read from the
      screen.
- [ ] Whether Watch mode should nudge the pointer to tell a still screen from a frozen one; with the `human`
      actuator there is no pointer to nudge.
- [ ] Drive mode: always aim (`precise`, about 1 s a tap), or also offer a fast mode without aiming?
- [ ] Human prompt timeout: 120 s by default, or no timeout while teaching?
