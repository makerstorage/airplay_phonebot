# GhostHand in the architecture

GhostHand is one **screen source + actuator pair** of the AI Phone Control System
([singlemachine.png](../singlemachine.png), [architecture.md](../architecture.md)). It runs on a Raspberry Pi 4
next to the phone or tablet.

```
 Agent Runtime (1)  ── e.g. Claude, on a Mac/server ──────────────┐
        │  Control API (HTTP, today: GhostHand :8890 over SSH)    │  not GhostHand
 Session Manager (2) ── today: a thin stand-in in app.py/phone.py ┘
        │
 ┌──────┴─────────────┬──────────────────────────┬───────────────────────────┐
 │ Device profile (3) │ Screen Source (4)        │ Actuator (5)              │
 │ ipad-air.yaml      │ airplay  ◄── GhostHand   │ ble-mouse ◄── GhostHand   │
 │ (data only)        │ UxPlay on the Pi         │ Pi Bluetooth = HID mouse  │
 └────────────────────┴──────────────────────────┴───────────────────────────┘
        ▲ frames (AirPlay, Wi-Fi)                 │ HID reports (BLE)
        └────────────── iPad / iPhone ◄───────────┘
```

| Diagram box | GhostHand part | Code |
|---|---|---|
| 4 Screen Source | AirPlay receiver (UxPlay) → JPEG frames | `receiver.py`, `screen.py` |
| 5 Actuator | BLE HID mouse + keyboard + Home key, with pointer calibration and aiming | `ble.py`, `phone.py`, `vision.py` (pointer finding) |
| 3 Device profile | calibration file only (`~/.hidagent/calibration.json`) | [device-profile.md](device-profile.md) |
| 2 Session, Control API | stand-in: HTTP API, lock, liveness check | `app.py` |
| 1 Agent | not in GhostHand (`agent.py` is an old planner/actor and will move out) | — |

## Interface documents

| Document | Boundary |
|---|---|
| [frame-and-gesture.md](frame-and-gesture.md) | the two data types that cross the boundaries |
| [screen-source.md](screen-source.md) | ScreenSource, `airplay` implementation |
| [actuator.md](actuator.md) | Actuator, `ble-mouse` implementation |
| [device-profile.md](device-profile.md) | the device data the actuator and session read |
| [control-api.md](control-api.md) | the HTTP API GhostHand offers today, and how it maps to the Control API |

## Rules

- All coordinates crossing a boundary are **fractions 0.0–1.0 of the visible screen**, origin top-left.
- Screen Source and Actuator never import each other. The actuator only gets a read-only view of the frames
  (the `Observer`), because a relative mouse has to find its own pointer to aim.
- Only the Control API may cross the network. Source and actuator run in one process on the Pi.
