# Control API — what GhostHand offers today

The Control API is the contract between the Agent (box 1) and the Session (box 2). GhostHand does not have a
real Session yet; `app.py` offers a small HTTP API that an agent can use directly. This is how the chess game on
the iPad was played: Claude on the Mac called it over SSH.

- Address: `http://127.0.0.1:8890` on the Pi, no auth, so use it over SSH.
- One action at a time: a second request while one runs gets `409 busy`.
- All coordinates are screen fractions 0..1.

| Call | Body | Diagram / architecture name |
|---|---|---|
| `GET /api/status` | | `status()` — `device` (BLE linked), `screen` (mirroring live), `calibrated`, `aspect` |
| `GET /api/frame.jpg` | | `observe()` — latest frame; `404` if not mirrored |
| `POST /api/tap` | `{"x", "y", "precise"?}` | `act([tap])` |
| `POST /api/swipe` | `{"x1", "y1", "x2", "y2"}` | `act([swipe])` |
| `POST /api/scroll` | `{"x", "y", "lines"}` | `act([scroll])` |
| `POST /api/type` | `{"text"}` | `act([text])` |
| `POST /api/key` | `{"text": "enter"}` | `act([key])` |
| `POST /api/home` | | `act([home])` |
| `POST /api/back` | | `act([back])` |
| `POST /api/calibrate/start`, `/finish` | | `calibrate()` |
| `POST /api/raw` | `{"text": "<line>"}` | debug only (`HIDAGENT_DEBUG=1`), one actuator protocol line |

Answers: `{"ok": true}`, or HTTP `409` with the reason (not calibrated, BLE not connected, phone not
mirrored, busy).

Example, one tap and a look:

```sh
ssh nerginer@ghosthand.local "curl -s -X POST -H 'Content-Type: application/json' \
  -d '{\"x\":0.39,\"y\":0.94,\"precise\":true}' 127.0.0.1:8890/api/tap"
ssh nerginer@ghosthand.local 'curl -s 127.0.0.1:8890/api/frame.jpg' > frame.jpg
```

## Missing compared to the contract

These belong to the Session, which lives outside GhostHand. Listed so whoever builds it knows what GhostHand
does not give:

- action ids and no-replay
- batches (`act(actions[])`) and the frame after the action returned with the result
- `changed` (did the screen change)
- typed errors (`not_calibrated`, `screen_unavailable`, …) instead of a 409 with text
- northbound task calls (`submit_task`, `approve`, `pause`, `cancel`, `subscribe_events`)
