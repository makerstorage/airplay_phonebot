# Device profile

Box 3 of the diagram: data, not code. It says how a device model is used, so the Session and the actuator don't
hard-code it. GhostHand has no profile files yet; this is what its two devices need.

```yaml
# profiles/ipad.yaml
name: ipad
os: ipados
screen: {aspect: 0.75, orientation: portrait}
avoid:                                  # screen fractions, gestures must not touch these
  - {name: top_left_corner, box: [0.0, 0.0, 0.02, 0.02]}   # opens Notification Center
  - {name: bottom_edge, box: [0.0, 0.99, 1.0, 1.0]}        # opens the Dock
edge_margin: 0.01                       # keep pointer moves this far from every edge
gestures:
  home: [{key: home}]                   # HID Home key; never a swipe from the corner
  back: [{swipe: [[0.005, 0.45], [0.6, 0.45]], hold_end: false}]
text: [hid_keyboard, clipboard]
calibration: ~/.hidagent/calibration.json   # span {w: 1121, h: 1530} for ble-mouse
```

```yaml
# profiles/iphone.yaml
name: iphone
os: ios
screen: {aspect: 0.4615, orientation: portrait}
avoid:
  - {name: home_indicator, box: [0.3, 0.97, 0.7, 1.0]}
gestures:
  home: [{key: home}, {swipe: [[0.5, 0.995], [0.5, 0.6]], hold_end: false}]
  back: [{swipe: [[0.005, 0.45], [0.6, 0.45]], hold_end: false}]
text: [hid_keyboard, clipboard]
calibration: ~/.hidagent/calibration.iphone.json
requires: [assistive_touch]
```

Today the same facts live in code and env vars: `POINTER_HOME=find`, `EDGE` and `go_home`/`go_back` in
`phone.py`, and one calibration file that is swapped by hand when changing device.
