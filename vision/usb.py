"""Reads the iPhone screen over the USB cable (no window, the Mac stays free).

macOS hides iOS screens from capture APIs until a process opts in with the
CoreMediaIO "allow screen capture devices" property. After that the iPhone shows
up as an AVFoundation device, like a camera.
"""

import threading
import time

import objc
import AVFoundation as AV
import CoreMedia
import CoreMediaIO as CMIO
import libdispatch
import Quartz
from Foundation import NSDate, NSObject, NSRunLoop
from PIL import Image

from vision.capture import Frame

_SampleDelegate = objc.protocolNamed("AVCaptureVideoDataOutputSampleBufferDelegate")


def allow_screen_capture_devices() -> None:
    addr = CMIO.CMIOObjectPropertyAddress(
        CMIO.kCMIOHardwarePropertyAllowScreenCaptureDevices,
        CMIO.kCMIOObjectPropertyScopeGlobal,
        CMIO.kCMIOObjectPropertyElementMain,
    )
    CMIO.CMIOObjectSetPropertyData(CMIO.kCMIOObjectSystemObject, addr, 0, objc.NULL, 4, (1).to_bytes(4, "little"))


def find_iphone(timeout_s: float = 15.0):
    """Waits for the iPhone to appear as a capture device."""
    allow_screen_capture_devices()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        session = AV.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
            [AV.AVCaptureDeviceTypeExternal], AV.AVMediaTypeMuxed, AV.AVCaptureDevicePositionUnspecified
        )
        for dev in session.devices():
            # The screen is the muxed "iOS Device", not the "iPhone Camera" (Continuity Camera)
            if str(dev.modelID()) == "iOS Device":
                return dev
        # Devices are announced through the run loop
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.25))
    return None


class _Delegate(NSObject, protocols=[_SampleDelegate]):
    def initWithOwner_(self, owner):
        self = objc.super(_Delegate, self).init()
        self.owner = owner
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample, connection):
        self.owner._on_sample(sample)


class UsbCapture:
    def __init__(self, max_long_edge: int = 1280, max_fps: float = 10):
        self.max_long_edge = max_long_edge
        self.min_interval = 1 / max_fps
        self._image: Image.Image | None = None
        self._last = 0.0
        self._lock = threading.Lock()
        self._session = None

    def start(self) -> None:
        dev = find_iphone()
        if dev is None:
            raise RuntimeError("No iPhone found. Plug it in with the cable, unlock it and tap 'Trust'.")
        inp, err = AV.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
        if inp is None:
            raise RuntimeError(f"Cannot open the iPhone screen: {err}")
        out = AV.AVCaptureVideoDataOutput.alloc().init()
        out.setVideoSettings_({Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA})
        out.setAlwaysDiscardsLateVideoFrames_(True)
        self._delegate = _Delegate.alloc().initWithOwner_(self)
        self._queue = libdispatch.dispatch_queue_create(b"phonebot.usb", None)
        out.setSampleBufferDelegate_queue_(self._delegate, self._queue)

        session = AV.AVCaptureSession.alloc().init()
        session.addInput_(inp)
        session.addOutput_(out)
        session.startRunning()
        self._session = session

    def stop(self) -> None:
        if self._session:
            self._session.stopRunning()
            self._session = None

    def grab(self) -> Frame:
        if self._session is None:
            self.start()
        deadline = time.monotonic() + 5
        while self._image is None:
            if time.monotonic() > deadline:
                raise RuntimeError("No picture from the iPhone yet. Is it unlocked?")
            time.sleep(0.05)
        with self._lock:
            img = self._image
        return Frame.from_phone(img, self.max_long_edge)

    def _on_sample(self, sample) -> None:
        # The phone can send 60 fps; converting every frame in Python is too slow
        now = time.monotonic()
        if now - self._last < self.min_interval:
            return
        self._last = now
        buf = CoreMedia.CMSampleBufferGetImageBuffer(sample)
        if buf is None:
            return
        Quartz.CVPixelBufferLockBaseAddress(buf, Quartz.kCVPixelBufferLock_ReadOnly)
        try:
            w = Quartz.CVPixelBufferGetWidth(buf)
            h = Quartz.CVPixelBufferGetHeight(buf)
            bpr = Quartz.CVPixelBufferGetBytesPerRow(buf)
            data = bytes(Quartz.CVPixelBufferGetBaseAddress(buf).as_buffer(bpr * h))
        finally:
            Quartz.CVPixelBufferUnlockBaseAddress(buf, Quartz.kCVPixelBufferLock_ReadOnly)
        img = Image.frombuffer("RGBA", (w, h), data, "raw", "BGRA", bpr, 1).convert("RGB")
        with self._lock:
            self._image = img
