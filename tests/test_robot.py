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
    assert m.log[:2] == ["G21", "G90"]
    # The stylus lifts before homing so it never drags on the glass
    assert m.log.index("G1 Z5.00 F1500") < m.log.index("G28 X Y R0")


def _write_setup(tmp_path, robot_section: str):
    machines = tmp_path / "machines"
    machines.mkdir()
    (machines / "fast.yaml").write_text("description: test\nbaud: 250000\nz_speed: 300\nscreen_box: [1, 2, 3, 4]\n"
                                        "firmware: {steps_per_mm: {z: 400}}\n")
    (machines / "slow.yaml").write_text("baud: 115200\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(robot_section)
    return cfg, machines


def test_load_config_uses_machine_file(tmp_path):
    from calib.run import load_calib_config
    from robot import load_config

    cfg, machines = _write_setup(tmp_path, "robot:\n  machine: fast\n  dry_run: true\n")
    c = load_config(cfg, machines_dir=machines)
    assert (c.name, c.baud, c.z_speed, c.dry_run) == ("fast", 250000, 300, True)
    assert c.firmware["steps_per_mm"]["z"] == 400
    calib = load_calib_config(c, cfg)
    assert c.screen_box == [1, 2, 3, 4]
    assert calib.file == "calibrations/fast.json"


def test_config_overrides_machine_and_cli_picks_machine(tmp_path):
    from robot import load_config

    cfg, machines = _write_setup(tmp_path, "robot:\n  machine: fast\n  baud: 9600\n")
    assert load_config(cfg, machines_dir=machines).baud == 9600
    assert load_config(cfg, machine="slow", machines_dir=machines).name == "slow"


def test_unknown_machine_lists_known(tmp_path):
    from robot import load_config

    cfg, machines = _write_setup(tmp_path, "robot:\n  machine: nope\n")
    with pytest.raises(ValueError, match="fast, slow"):
        load_config(cfg, machines_dir=machines)


def test_repo_machine_files_load():
    from robot import list_machines, load_config

    for name in list_machines():
        assert load_config(machine=name).name == name


def _cam(**kw):
    return GcodeBuilder(RobotConfig(**{"z_mode": "cam", "cam_half_turn": 4.0, "z_speed": 1200, "tap_hold_ms": 0, **kw}))


def test_cam_tap_is_two_forward_half_turns():
    assert _cam().tap(10, 20) == [
        "G0 X10.00 Y20.00 F3000",
        "G1 Z4.00 F1200",
        "G1 Z8.00 F1200",
        "G92 Z0",
    ]


def test_cam_pen_up_and_down_only_turn_when_needed():
    g = _cam()
    assert g.pen_up() == []  # already up: a full turn would tap the glass
    assert g.pen_down() == ["G1 Z4.00 F1200"]
    assert g.pen_down() == []
    assert g.pen_up() == ["G1 Z8.00 F1200", "G92 Z0"]


def test_cam_hold_and_double_tap():
    g = _cam(tap_hold_ms=100)
    assert g.tap(1, 2)[2] == "G4 P100"
    d = _cam().double_tap(1, 2)
    assert d == ["G0 X1.00 Y2.00 F3000", "G1 Z4.00 F1200", "G1 Z8.00 F1200", "G92 Z0",
                 "G1 Z4.00 F1200", "G1 Z8.00 F1200", "G92 Z0"]


def test_cam_swipe_out_of_bounds_keeps_state():
    g = _cam(x_max=100, y_max=100)
    with pytest.raises(ValueError):
        g.swipe(10, 10, 10, 150)
    assert g.pen_is_down is False


def test_cam_setup_zeroes_z_and_sets_limits():
    m = Machine(RobotConfig(dry_run=True, z_mode="cam", z_max_speed=20, z_accel=500, home_on_start=False))
    m.connect()
    assert m.log == ["G21", "G90", "G92 Z0", "M203 Z20", "M201 Z500"]
    assert "M92 Y100" in GcodeBuilder(RobotConfig(dry_run=True, y_steps_per_mm=100)).setup()


def test_home_by_order_never_homes_on_connect_and_refuses_taps_until_homed():
    cfg = RobotConfig(dry_run=False, home_by_order=True, home_on_start=True, z_mode="cam")
    assert "G28 X Y R0" not in GcodeBuilder(cfg).setup()

    class Wire(Machine):  # no serial port: just collect the lines
        def send(self, lines):
            self.log += lines

    m = Wire(cfg)
    assert not m.homed
    with pytest.raises(RuntimeError, match="not homed"):
        m.tap(10, 10)
    m.home()
    assert m.log == ["G28 X Y R0", "M400"] and m.homed
    m.tap(10, 10)
