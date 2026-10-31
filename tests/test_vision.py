from PIL import Image

from vision import ScreenCapture, VisionConfig


def test_crop_and_downscale(monkeypatch):
    # 3840x2160 fullscreen window, phone fitted to the height and centered
    raw = Image.new("RGB", (3840, 2160))

    cap = ScreenCapture(VisionConfig(max_long_edge=1280))
    monkeypatch.setattr(cap, "find_window", lambda: 1)
    monkeypatch.setattr(cap, "_capture_window", lambda _id: raw)

    frame = cap.grab()
    assert frame.phone.size == (996, 2160)
    assert max(frame.model.size) == 1280
    x, y = frame.to_phone(0, 1280)
    assert x == 0 and round(y) == 2160
