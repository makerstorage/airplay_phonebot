# Phonebot

An AI uses a real iPhone: the screen comes in over AirPlay (UxPlay), Claude decides, a G-code machine taps.

- Code: `robot/` (G-code + serial), `actuator/`, `calib/` (phone pixel → mm), `agent/`, `web/`, `vision/`, `teach/`.
- Machines: `machines/<name>.yaml`, picked by `robot.machine` in `config.yaml` or `--machine`. Calibration per machine: `calibrations/<name>.json`.
- The phone is not in a fixed holder: calibrate again when it has moved (Calibrate button on the control page, or `python -m calib --home`). The machine finds the screen itself; no screen box is measured by hand.
- `mks-gen13` never homes on connect (`home_by_order`): taps are refused until the user orders Home (button on the control page).
- Current machine: `machines/mks-gen13.yaml`. Read it first: it has the tested facts, firmware build/flash steps and TODOs.
- Manual serial: `.venv/bin/python scripts/serial_bot.py serve /dev/cu.usbserial-A1083DYR 250000` (background), then `... send "M114"`.

## Rules for the machine
- The user gives the orders. Send only what they say, report the result in a line or two, then wait. Don't propose plans or tell the user what to do.
- Never connect or move without the user's order. Connecting resets the board and the position is lost.
- Never home Z (no Z switch). Home X/Y only when the user says.
- Software limits block moves below 0. If a move needs it, set the position with G92 first and say so.
- Save every result the user confirms to the machine file.

## Style
Short, clear answers. Ask about unknowns instead of guessing.
