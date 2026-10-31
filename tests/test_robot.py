import pytest

from robot import GcodeBuilder, Machine, RobotConfig


def test_tap_sequence():
    g = GcodeBuilder(RobotConfig())
    assert g.tap(10, 20) == [
        "G1 Z5.00 F1500",
        "G0 X10.00 Y20.00 F3000",
        "G1 Z0.00 F1500",
        "G4 P80",
        "G1 Z5.00 F1500",
    ]


def test_dwell_seconds_for_grbl():
    g = GcodeBuilder(RobotConfig(dwell_in_seconds=True))
    assert g.dwell(800) == ["G4 P0.800"]


def test_swipe_moves_with_pen_down():
    lines = GcodeBuilder(RobotConfig()).swipe(10, 100, 10, 20)
    assert lines[2] == "G1 Z0.00 F1500"
    assert lines[3] == "G1 X10.00 Y20.00 F1500"
    assert lines[4] == "G1 Z5.00 F1500"


def test_out_of_bounds_refused():
    g = GcodeBuilder(RobotConfig(x_max=100, y_max=100))
    with pytest.raises(ValueError):
        g.tap(150, 50)
    with pytest.raises(ValueError):
        g.swipe(10, 10, 10, 150)


def test_dry_run_logs_setup_with_home():
    m = Machine(RobotConfig(dry_run=True))
    m.connect()
    assert m.log[:3] == ["G21", "G90", "G28 X0 Y0"]
