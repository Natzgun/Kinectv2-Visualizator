"""Kinect acquisition on a worker thread; the UI never owns native frames."""

from pathlib import Path
from math import isfinite
from threading import Lock
from time import monotonic

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

def available_pipelines():
    from pylibfreenect2 import libfreenect2 as bindings

    return {
        name: getattr(bindings, name)
        for name in ("CpuPacketPipeline", "OpenGLPacketPipeline", "OpenCLPacketPipeline",
                     "OpenCLKdePacketPipeline", "CudaPacketPipeline")
        if hasattr(bindings, name)
    }


def display_image(name, data):
    """Convert sensor data into an owned RGB888 image for Qt."""
    if name in ("Color", "Registered"):
        return np.ascontiguousarray(data[:, :, (2, 1, 0)])
    if name in ("Depth", "Undistorted", "Big depth"):
        gray = np.clip(data * (255.0 / 4500.0), 0, 255).astype(np.uint8)
    elif name == "Infrared":
        gray = np.clip(data * (255.0 / 65535.0), 0, 255).astype(np.uint8)
    elif name == "Color-depth map":
        gray = np.where(data >= 0, data * (255.0 / (1920 * 1080)), 0)
        gray = np.rint(np.clip(gray, 0, 255)).astype(np.uint8)
    else:
        raise ValueError(name)
    return np.repeat(gray[:, :, None], 3, axis=2)


class CaptureThread(QThread):
    frames_ready = pyqtSignal(object)
    device_ready = pyqtSignal(object)
    point_ready = pyqtSignal(object)
    setting_result = pyqtSignal(str)
    capture_error = pyqtSignal(str)
    snapshot_saved = pyqtSignal(str)

    def __init__(self, pipeline="CpuPacketPipeline", extended=False, settings=None, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.extended = extended
        self.settings = settings or {}
        self._lock = Lock()
        self._snapshot_path = None
        self._point = None
        self._color_setting_request = None

    def save_next_frame(self, path: Path):
        with self._lock:
            self._snapshot_path = path

    def inspect_point(self, column, row):
        with self._lock:
            self._point = (column, row)

    def query_color_setting(self, command, value=None, floating=False):
        with self._lock:
            self._color_setting_request = (command, value, floating)

    def run(self):
        device = None
        listener = None
        sensor = None
        try:
            from pylibfreenect2 import (
                Frame, FrameType, Freenect2, Registration, SyncMultiFrameListener,
            )

            sensor = Freenect2()
            if sensor.enumerateDevices() < 1:
                raise RuntimeError("No Kinect v2 detected. Check the USB 3 connection.")
            pipeline = available_pipelines()[self.pipeline]()
            settings = self.settings
            rgb = settings.get("rgb", True)
            depth_enabled = settings.get("depth", True)
            if not rgb and not depth_enabled:
                raise ValueError("Enable color or depth before starting")
            serial = settings.get("serial")
            device = sensor.openDevice(serial, pipeline=pipeline) if serial else sensor.openDefaultDevice(pipeline=pipeline)
            mask = (FrameType.Color if rgb else 0) | (
                FrameType.Ir | FrameType.Depth if depth_enabled else 0
            )
            listener = SyncMultiFrameListener(mask)
            if rgb:
                device.setColorFrameListener(listener)
            if depth_enabled:
                device.setIrAndDepthFrameListener(listener)
            if depth_enabled and any((
                settings.get("min_depth", 0.5) != 0.5,
                settings.get("max_depth", 4.5) != 4.5,
                not settings.get("bilateral", True),
                not settings.get("edge_aware", True),
            )):
                device.setDepthConfiguration(
                    settings["min_depth"], settings["max_depth"],
                    settings["bilateral"], settings["edge_aware"],
                )
            device.startStreams(rgb, depth_enabled)
            # Camera control commands require initialized streams on this device.
            if rgb and settings.get("exposure") == "Auto":
                device.setColorAutoExposure(settings.get("compensation", 0.0))
            elif rgb and settings.get("exposure") == "Manual":
                device.setColorManualExposure(settings["exposure_ms"], settings["gain"])
            elif rgb and settings.get("exposure") == "Semi-auto":
                device.setColorSemiAutoExposure(settings["exposure_ms"])
            if settings.get("set_led"):
                device.setLedStatus(settings["led_id"], settings["led_level"],
                                    interval_ms=settings["blink_ms"])
            ir_params = device.getIrCameraParams()
            color_params = device.getColorCameraParams()
            registration = Registration(ir_params, color_params) if depth_enabled else None
            undistorted = Frame(512, 424, 4) if depth_enabled else None
            registered = Frame(512, 424, 4) if rgb and depth_enabled else None
            extended = self.extended and rgb and depth_enabled
            bigdepth = Frame(1920, 1082, 4) if extended else None
            color_depth_map = np.zeros(424 * 512, dtype=np.int32) if extended else None
            color_keys = ("fx", "fy", "cx", "cy", "shift_d", "shift_m") + tuple(
                f"{axis}_{term}" for axis in ("mx", "my") for term in
                ("x3y0", "x0y3", "x2y1", "x1y2", "x2y0", "x0y2", "x1y1", "x1y0", "x0y1", "x0y0")
            )
            info = {
                "serial": device.getSerialNumber().decode(),
                "firmware": device.getFirmwareVersion().decode(),
                "pipeline": self.pipeline,
                "rgb_enabled": rgb,
                "depth_enabled": depth_enabled,
                "ir": {key: getattr(ir_params, key) for key in
                       ("fx", "fy", "cx", "cy", "k1", "k2", "k3", "p1", "p2")},
                "color": {key: getattr(color_params, key) for key in color_keys},
            }
            self.device_ready.emit(info)

            next_preview = 0.0
            while not self.isInterruptionRequested():
                with self._lock:
                    command_request = self._color_setting_request
                    self._color_setting_request = None
                if command_request is not None and rgb:
                    command, value, floating = command_request
                    try:
                        if value is None:
                            result = (device.getColorSettingFloat(command) if floating
                                      else device.getColorSetting(command))
                            self.setting_result.emit(f"RGB command {command}: {result}")
                        else:
                            device.setColorSetting(command, value)
                            self.setting_result.emit(f"RGB command {command}: sent {value}")
                    except Exception as error:
                        self.setting_result.emit(f"RGB command {command}: {error}")
                frames = listener.waitForNewFrame(milliseconds=500)
                if frames is None:
                    continue
                with self._lock:
                    snapshot_pending = self._snapshot_path is not None
                    point = self._point
                    self._point = None
                now = monotonic()
                if now < next_preview and not snapshot_pending and point is None:
                    listener.release(frames)
                    continue
                next_preview = now + 1 / settings.get("preview_fps", 15)
                try:
                    payload = {}
                    for frame_name, label in (("color", "Color"), ("ir", "Infrared"), ("depth", "Depth")):
                        if (frame_name == "color" and not rgb) or (frame_name != "color" and not depth_enabled):
                            continue
                        frame = frames[frame_name]
                        payload[label] = frame.asarray().copy()
                        for field in ("sequence", "timestamp", "status", "format", "exposure", "gain", "gamma"):
                            payload[f"{frame_name}_{field}"] = getattr(frame, field)
                    primary = frames["depth"] if depth_enabled else frames["color"]
                    payload["sequence"] = primary.sequence
                    payload["timestamp"] = primary.timestamp
                    if depth_enabled and rgb:
                        registration.apply(frames["color"], frames["depth"], undistorted, registered,
                                           bigdepth=bigdepth, color_depth_map=color_depth_map)
                        payload["Registered"] = registered.asarray(np.uint8).copy()
                    elif depth_enabled:
                        registration.undistortDepth(frames["depth"], undistorted)
                    if depth_enabled:
                        payload["Undistorted"] = undistorted.asarray(np.float32).copy()
                    if extended:
                        payload["Big depth"] = bigdepth.asarray(np.float32).copy()
                        payload["Color-depth map"] = color_depth_map.reshape(424, 512).copy()
                    if point is not None and depth_enabled:
                        column, row = point
                        if 0 <= column < 512 and 0 <= row < 424:
                            coords = registration.getPointXYZ(undistorted, row, column)
                            result = {"column": column, "row": row, "xyz": coords}
                            if rgb and isfinite(coords[2]) and coords[2] > 0:
                                result["xyz_bgr"] = registration.getPointXYZRGB(
                                    undistorted, registered, row, column)
                                uv = registration.applyPoint(
                                    column, row, float(frames["depth"].asarray()[row, column]))
                                if all(isfinite(value) for value in uv):
                                    result["color_uv"] = uv
                            self.point_ready.emit(result)
                finally:
                    listener.release(frames)

                with self._lock:
                    path = self._snapshot_path
                    self._snapshot_path = None
                if path is not None:
                    calibration = {
                        f"calibration_{camera}_{key}": value
                        for camera in ("ir", "color") for key, value in info[camera].items()
                    }
                    np.savez_compressed(path, **payload, **calibration,
                                        serial=info["serial"], firmware=info["firmware"],
                                        pipeline=self.pipeline)
                    self.snapshot_saved.emit(str(path))
                if not self.isInterruptionRequested():
                    self.frames_ready.emit(payload)
        except Exception as error:
            self.capture_error.emit(str(error))
        finally:
            if device is not None:
                try:
                    device.stop()
                finally:
                    device.close()
            # Keep the native listener and sensor alive through device shutdown.
            _ = listener, sensor
