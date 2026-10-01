"""PyQt6 explorer for the streams exposed by libfreenect2."""

import sys
from datetime import datetime
from pathlib import Path
from time import monotonic

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from capture import CaptureThread, available_pipelines, display_image
from gestures import GestureThread


HAND_EDGES = ((0, 1), (1, 2), (2, 3), (3, 4),
              (0, 5), (5, 6), (6, 7), (7, 8),
              (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16),
              (13, 17), (17, 18), (18, 19), (19, 20), (0, 17))


class ImageView(QLabel):
    clicked = pyqtSignal(float, float)

    def __init__(self):
        super().__init__("Connect a Kinect v2 and press Start")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background: #161b23; color: #dce6f1; padding: 10px;")
        self._size = None

    def show_array(self, array, hands=()):
        height, width, _ = array.shape
        image = QImage(array.data, width, height, array.strides[0],
                       QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            960, 640, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        if hands:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for hand in hands:
                points = hand["landmarks"]
                painter.setPen(QPen(QColor("#24d6bc"), 2))
                for start, end in HAND_EDGES:
                    a, b = points[start], points[end]
                    painter.drawLine(round(a[0] * pixmap.width()), round(a[1] * pixmap.height()),
                                     round(b[0] * pixmap.width()), round(b[1] * pixmap.height()))
                painter.setPen(QPen(QColor("#ffdd72"), 4))
                for x, y, _ in points:
                    painter.drawPoint(round(x * pixmap.width()), round(y * pixmap.height()))
            painter.end()
        self.setPixmap(pixmap)
        self._size = (width, height)

    def mousePressEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is not None and self._size is not None:
            x = (event.position().x() - (self.width() - pixmap.width()) / 2) / pixmap.width()
            y = (event.position().y() - (self.height() - pixmap.height()) / 2) / pixmap.height()
            if 0 <= x < 1 and 0 <= y < 1:
                self.clicked.emit(x, y)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kinect v2 Explorer")
        self.resize(1120, 780)
        self.worker = None
        self.gesture_worker = None
        self.gesture_overlay = None
        self.gesture_received_at = 0.0
        self.latest = None
        self.info = None
        self.capability_status = "No capture verified in this session"
        self.capability_probe_complete = False

        self.start_button = QPushButton("Start capture")
        self.stop_button = QPushButton("Stop capture")
        self.snapshot_button = QPushButton("Save frame data (.npz)")
        self.stop_button.setEnabled(False)
        self.snapshot_button.setEnabled(False)
        self.pipeline = QComboBox()
        self.pipeline.addItems(available_pipelines())
        self.pipeline.setToolTip("Depth processing backend; CPU works without GPU support")
        self.extended = QCheckBox("Extended registration")
        self.extended.setToolTip("Include full-resolution depth and color-depth pixel mapping in snapshots")
        self.rgb_stream = QCheckBox("Color stream")
        self.rgb_stream.setChecked(True)
        self.depth_stream = QCheckBox("Infrared + depth streams")
        self.depth_stream.setChecked(True)
        self.preview_fps = QSpinBox()
        self.preview_fps.setRange(1, 30)
        self.preview_fps.setValue(15)
        self.preview_fps.setSuffix(" preview FPS")
        self.gesture_mode = QComboBox()
        self.gesture_mode.addItems(("Off", "Gestures", "Landmarks"))
        self.hand_count = QSpinBox()
        self.hand_count.setRange(1, 4)
        self.hand_count.setValue(2)
        self.hand_count.setSuffix(" hands max")
        self.gesture_status = QLabel("Hand analysis off")
        self.gesture_mode.currentTextChanged.connect(
            lambda mode: self.gesture_status.setText(
                "Hand analysis off" if mode == "Off" else f"Ready: {mode}"
            )
        )
        self.devices = QComboBox()
        self.devices.addItem("First available device", None)
        self.refresh_button = QPushButton("Refresh devices")
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.settings_panel = QGroupBox("Sensor settings (applied when capture starts)")
        settings_layout = QGridLayout(self.settings_panel)

        self.min_depth = QDoubleSpinBox()
        self.min_depth.setRange(0, 9.9)
        self.min_depth.setValue(0.5)
        self.min_depth.setSuffix(" m min")
        self.max_depth = QDoubleSpinBox()
        self.max_depth.setRange(0.1, 10)
        self.max_depth.setValue(4.5)
        self.max_depth.setSuffix(" m max")
        self.bilateral = QCheckBox("Bilateral filter")
        self.bilateral.setChecked(True)
        self.edge_aware = QCheckBox("Edge-aware filter")
        self.edge_aware.setChecked(True)
        self.exposure = QComboBox()
        self.exposure.addItems(("Default", "Auto", "Semi-auto", "Manual"))
        self.compensation = QDoubleSpinBox()
        self.compensation.setRange(-2, 2)
        self.compensation.setSingleStep(0.1)
        self.compensation.setPrefix("Compensation ")
        self.exposure_ms = QDoubleSpinBox()
        self.exposure_ms.setRange(0.1, 66)
        self.exposure_ms.setValue(10)
        self.exposure_ms.setSuffix(" ms")
        self.gain = QDoubleSpinBox()
        self.gain.setRange(1, 4)
        self.gain.setSingleStep(0.1)
        self.gain.setValue(1)
        self.gain.setPrefix("Gain ")
        self.set_led = QCheckBox("Set LED")
        self.led_id = QSpinBox()
        self.led_id.setRange(0, 1)
        self.led_id.setPrefix("LED ")
        self.led_level = QSpinBox()
        self.led_level.setRange(0, 1000)
        self.led_level.setValue(500)
        self.led_level.setPrefix("Level ")
        self.blink_ms = QSpinBox()
        self.blink_ms.setRange(0, 10000)
        self.blink_ms.setSuffix(" ms blink (0 = steady)")

        from pylibfreenect2 import ColorSettingCommand

        self.rgb_command = QComboBox()
        for command in ColorSettingCommand:
            self.rgb_command.addItem(f"{command.name} ({command.value})", command.value)
        self.rgb_command.setCurrentIndex(self.rgb_command.findData(83))
        self.rgb_value = QLineEdit()
        self.rgb_value.setPlaceholderText("Value to write")
        self.rgb_float = QCheckBox("Float")
        self.read_setting = QPushButton("Read RGB setting")
        self.write_setting = QPushButton("Write RGB setting")
        self.read_setting.setEnabled(False)
        self.write_setting.setEnabled(False)
        self.read_setting.clicked.connect(self.query_rgb_setting)
        self.write_setting.clicked.connect(self.write_rgb_setting)

        for row, widgets in enumerate((
            (self.min_depth, self.max_depth, self.bilateral, self.edge_aware),
            (self.exposure, self.compensation, self.exposure_ms, self.gain),
            (self.set_led, self.led_id, self.led_level, self.blink_ms),
        )):
            for column, widget in enumerate(widgets):
                settings_layout.addWidget(widget, row, column)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Processing pipeline:"))
        controls.addWidget(self.pipeline)
        controls.addWidget(self.extended)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.snapshot_button)
        controls.addStretch()
        stream_controls = QHBoxLayout()
        stream_controls.addWidget(QLabel("Device:"))
        stream_controls.addWidget(self.devices)
        stream_controls.addWidget(self.refresh_button)
        stream_controls.addWidget(self.rgb_stream)
        stream_controls.addWidget(self.depth_stream)
        stream_controls.addWidget(self.preview_fps)
        stream_controls.addStretch()
        gesture_controls = QHBoxLayout()
        gesture_controls.addWidget(QLabel("Hand analysis:"))
        gesture_controls.addWidget(self.gesture_mode)
        gesture_controls.addWidget(self.hand_count)
        gesture_controls.addWidget(self.gesture_status, 1)
        setting_controls = QHBoxLayout()
        setting_controls.addWidget(QLabel("Advanced RGB setting:"))
        for widget in (self.rgb_command, self.rgb_value, self.rgb_float,
                       self.read_setting, self.write_setting):
            setting_controls.addWidget(widget)

        self.tabs = QTabWidget()
        self.views = {}
        for name in ("Color", "Infrared", "Depth", "Undistorted", "Registered",
                     "Big depth", "Color-depth map"):
            view = ImageView()
            scroll = QScrollArea()
            scroll.setWidget(view)
            scroll.setWidgetResizable(True)
            self.views[name] = view
            self.tabs.addTab(scroll, name)
            if name in ("Depth", "Undistorted"):
                view.clicked.connect(self.inspect_depth)
        for index in (5, 6):
            self.tabs.setTabEnabled(index, False)
        self.extended.toggled.connect(self.update_tabs)
        self.rgb_stream.toggled.connect(self.update_tabs)
        self.depth_stream.toggled.connect(self.update_tabs)

        self.capabilities = QTextEdit()
        self.capabilities.setReadOnly(True)
        self.tabs.addTab(self.capabilities, "Capabilities")
        self.update_capabilities()

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(155)
        self.details.setPlainText(
            "Color: 1920×1080 BGRA | IR and depth: 512×424 float32. "
            "Registered: color aligned to depth; Undistorted: corrected depth. "
            "Click the depth image to inspect distance and 3D coordinates. "
            "Audio and skeletal tracking are not provided by libfreenect2. "
            "Hand gestures are available separately through MediaPipe."
        )
        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addLayout(stream_controls)
        layout.addLayout(gesture_controls)
        layout.addWidget(self.settings_panel)
        layout.addLayout(setting_controls)
        layout.addWidget(self.tabs)
        layout.addWidget(self.details)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Disconnected")

        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(self.stop_capture)
        self.snapshot_button.clicked.connect(self.save_snapshot)

    def refresh_devices(self):
        from pylibfreenect2 import Freenect2

        self.devices.clear()
        self.devices.addItem("First available device", None)
        try:
            sensor = Freenect2()
            for index in range(sensor.enumerateDevices()):
                serial = sensor.getDeviceSerialNumber(index).decode()
                self.devices.addItem(f"Device {index}: {serial}", serial)
        except Exception as error:
            QMessageBox.warning(self, "Device discovery failed", str(error))
        self.update_capabilities()

    def update_tabs(self):
        rgb, depth = self.rgb_stream.isChecked(), self.depth_stream.isChecked()
        enabled = (rgb, depth, depth, depth, rgb and depth,
                   rgb and depth and self.extended.isChecked(),
                   rgb and depth and self.extended.isChecked())
        for index, active in enumerate(enabled):
            self.tabs.setTabEnabled(index, active)
        if self.tabs.currentIndex() < len(enabled) and not enabled[self.tabs.currentIndex()]:
            self.tabs.setCurrentIndex(next((i for i, active in enumerate(enabled) if active), 7))

    def query_rgb_setting(self):
        if self.worker is not None:
            self.worker.query_color_setting(self.rgb_command.currentData(), floating=self.rgb_float.isChecked())

    def write_rgb_setting(self):
        try:
            value = (float(self.rgb_value.text()) if self.rgb_float.isChecked()
                     else int(self.rgb_value.text()))
        except ValueError:
            QMessageBox.warning(self, "Invalid RGB value", "Enter a numeric value first.")
            return
        if self.worker is not None:
            self.worker.query_color_setting(self.rgb_command.currentData(), value,
                                            self.rgb_float.isChecked())

    def update_capabilities(self):
        from pylibfreenect2 import (
            ColorCameraParams, ColorSettingCommand, Frame, FrameFormat, FrameMap,
            Freenect2, Freenect2Device, Freenect2Replay, IrCameraParams,
            Registration, SyncMultiFrameListener,
        )

        native_only = (
            "Native replay: only raw .depth packets are processed (not .npz or .jpg)",
            "Skeleton and microphone: not provided by the public image-stream API",
            "Hand gestures: optional MediaPipe analysis of the color stream",
        )
        lines = ["Python API exported (not necessarily tested on this device)", "",
                 "Available pipelines: " + ", ".join(available_pipelines()),
                 "Frame formats: " + ", ".join(f"{item.name}={item.value}" for item in FrameFormat),
                 f"Named RGB commands: {len(ColorSettingCommand)}",
                 f"Discovered devices: {max(0, self.devices.count() - 1)} (press Refresh devices)",
                 "Last capture: " + self.capability_status, ""]
        for title, interface in (("Discovery", Freenect2), ("Device", Freenect2Device),
                                 ("Frame", Frame), ("Frame map", FrameMap),
                                 ("Listener", SyncMultiFrameListener),
                                 ("RGB calibration", ColorCameraParams),
                                 ("IR calibration", IrCameraParams),
                                 ("Registration", Registration), ("Raw replay", Freenect2Replay)):
            lines.append(title + ": " + ", ".join(
                name for name in dir(interface) if not name.startswith("_")))
        lines.extend(("", "Logger: createConsoleLogger, getGlobalLogger, setGlobalLogger",
                      "", "Native limitations", *native_only))
        self.capabilities.setPlainText("\n".join(lines))

    def start_capture(self):
        if self.worker is not None or self.gesture_worker is not None:
            return
        if self.gesture_mode.currentText() != "Off" and not self.rgb_stream.isChecked():
            QMessageBox.warning(self, "Color stream required", "Hand analysis needs the color stream.")
            return
        if not self.rgb_stream.isChecked() and not self.depth_stream.isChecked():
            QMessageBox.warning(self, "No streams selected", "Enable color or infrared/depth.")
            return
        if self.min_depth.value() >= self.max_depth.value():
            QMessageBox.warning(self, "Invalid depth range", "Minimum depth must be smaller than maximum depth.")
            return
        settings = {
            "min_depth": self.min_depth.value(), "max_depth": self.max_depth.value(),
            "bilateral": self.bilateral.isChecked(),
            "edge_aware": self.edge_aware.isChecked(),
            "exposure": self.exposure.currentText(),
            "compensation": self.compensation.value(),
            "exposure_ms": self.exposure_ms.value(), "gain": self.gain.value(),
            "set_led": self.set_led.isChecked(), "led_id": self.led_id.value(),
            "led_level": self.led_level.value(), "blink_ms": self.blink_ms.value(),
            "rgb": self.rgb_stream.isChecked(), "depth": self.depth_stream.isChecked(),
            "serial": self.devices.currentData(),
            "preview_fps": self.preview_fps.value(),
        }
        self.worker = CaptureThread(self.pipeline.currentText(), self.extended.isChecked(), settings)
        self.gesture_overlay = None
        self.gesture_status.setText("Hand analysis off")
        if self.gesture_mode.currentText() != "Off":
            self.gesture_worker = GestureThread(self.gesture_mode.currentText(), self.hand_count.value())
            self.gesture_worker.results_ready.connect(self.on_gestures)
            self.gesture_worker.analysis_error.connect(self.on_gesture_error)
            self.gesture_worker.finished.connect(self.on_gesture_finished)
            self.gesture_status.setText("Loading hand model...")
            self.gesture_worker.start()
        self.capability_probe_complete = False
        self.worker.device_ready.connect(self.on_device_ready)
        self.worker.point_ready.connect(self.on_point)
        self.worker.setting_result.connect(self.statusBar().showMessage)
        self.worker.frames_ready.connect(self.on_frames)
        self.worker.capture_error.connect(self.on_error)
        self.worker.snapshot_saved.connect(
            lambda path: self.statusBar().showMessage(f"Saved: {path}")
        )
        self.worker.finished.connect(self.on_finished)
        self.pipeline.setEnabled(False)
        self.extended.setEnabled(False)
        self.settings_panel.setEnabled(False)
        self.devices.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.rgb_stream.setEnabled(False)
        self.depth_stream.setEnabled(False)
        self.preview_fps.setEnabled(False)
        self.gesture_mode.setEnabled(False)
        self.hand_count.setEnabled(False)
        self.read_setting.setEnabled(settings["rgb"])
        self.write_setting.setEnabled(settings["rgb"])
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.statusBar().showMessage("Connecting...")
        self.worker.start()

    def stop_capture(self):
        if self.gesture_worker is not None:
            self.gesture_worker.stop()
        if self.worker is not None:
            self.stop_button.setEnabled(False)
            self.worker.requestInterruption()
            self.snapshot_button.setEnabled(False)
            self.statusBar().showMessage("Stopping capture...")

    def on_finished(self):
        if self.gesture_worker is not None:
            self.gesture_worker.stop()
        self.worker = None
        self.start_button.setEnabled(self.gesture_worker is None)
        self.stop_button.setEnabled(False)
        self.snapshot_button.setEnabled(False)
        self.pipeline.setEnabled(True)
        self.extended.setEnabled(True)
        self.settings_panel.setEnabled(True)
        self.devices.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.rgb_stream.setEnabled(True)
        self.depth_stream.setEnabled(True)
        self.preview_fps.setEnabled(True)
        self.gesture_mode.setEnabled(True)
        self.hand_count.setEnabled(True)
        self.read_setting.setEnabled(False)
        self.write_setting.setEnabled(False)
        self.statusBar().showMessage("Disconnected")

    def on_gesture_finished(self):
        self.gesture_worker = None
        if self.worker is None:
            self.start_button.setEnabled(True)

    def on_gesture_error(self, message):
        self.gesture_status.setText(f"Hand analysis error: {message}")
        if self.gesture_worker is not None:
            self.gesture_worker.stop()

    def on_gestures(self, result):
        if self.worker is None or self.worker.isInterruptionRequested():
            return
        self.gesture_overlay = result["hands"]
        self.gesture_received_at = monotonic()
        if result["hands"]:
            labels = []
            for hand in result["hands"]:
                description = (f"{hand['gesture']} ({hand['score']:.0%})"
                               if result["mode"] == "Gestures" else "21 landmarks")
                distance = (f" ~{hand['wrist_depth_m']:.2f} m"
                            if "wrist_depth_m" in hand else "")
                labels.append(f"{hand['handedness']}: {description}{distance}")
            summary = ", ".join(labels)
            self.gesture_status.setText(summary)
        else:
            self.gesture_status.setText("No hands detected")

    def on_device_ready(self, info):
        self.info = info
        lines = [f"Serial: {info['serial']} | Firmware: {info['firmware']} | "
                 f"Pipeline: {info['pipeline']} | Color: {info['rgb_enabled']} | Depth: {info['depth_enabled']}"]
        for camera in ("color", "ir"):
            params = ", ".join(f"{key}={value:.2f}" for key, value in info[camera].items())
            lines.append(f"{camera.upper()} intrinsics: {params}")
        self.details.setPlainText("\n".join(lines))

    def on_frames(self, frames):
        if self.worker is None or self.worker.isInterruptionRequested():
            return
        self.latest = frames
        if self.gesture_worker is not None:
            self.gesture_worker.submit(frames)
        if not self.capability_probe_complete:
            captured = ", ".join(name for name in self.views if name in frames)
            self.capability_status = f"{captured} via {self.info['pipeline'] if self.info else 'device'}"
            self.capability_probe_complete = True
            self.update_capabilities()
        active = self.tabs.tabText(self.tabs.currentIndex())
        if active in self.views and active in frames:
            overlay = (self.gesture_overlay if active == "Color" and
                       monotonic() - self.gesture_received_at < 0.5 else ())
            self.views[active].show_array(display_image(active, frames[active]), overlay)
        self.snapshot_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Streaming | sequence {frames['sequence']} | sensor timestamp {frames['timestamp']} (0.125 ms units)"
        )

    def inspect_depth(self, x, y):
        if self.latest is None or "Undistorted" not in self.latest:
            return
        data = self.latest["Undistorted"]
        row = min(int(y * data.shape[0]), data.shape[0] - 1)
        col = min(int(x * data.shape[1]), data.shape[1] - 1)
        if self.worker is not None:
            self.worker.inspect_point(col, row)

    def on_point(self, result):
        x, y, z = result["xyz"]
        col, row = result["column"], result["row"]
        if not (0 < z < float("inf")):
            self.statusBar().showMessage(f"Pixel ({col}, {row}): no valid depth")
            return
        color = result.get("xyz_bgr")
        extra = f" | BGR {color[3:]}" if color else ""
        if "color_uv" in result:
            extra += f" | color UV {result['color_uv']}"
        self.statusBar().showMessage(
            f"Pixel ({col}, {row}): {z * 1000:.0f} mm | "
            f"3D ({x:.3f}, {y:.3f}, {z:.3f}) m{extra}"
        )

    def save_snapshot(self):
        if self.worker is None or self.worker.isInterruptionRequested() or self.latest is None:
            return
        suggested = f"kinect-{datetime.now():%Y%m%d-%H%M%S}.npz"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save raw sensor frames", suggested, "NumPy archive (*.npz)"
        )
        if filename:
            path = Path(filename)
            self.worker.save_next_frame(path if path.suffix == ".npz" else path.with_suffix(".npz"))
            self.statusBar().showMessage("Saving next frame...")

    def on_error(self, message):
        QMessageBox.warning(self, "Kinect capture error", message)

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.requestInterruption()
            if not self.worker.wait(5000):
                event.ignore()
                self.statusBar().showMessage("Waiting for Kinect to stop...")
                return
        if self.gesture_worker is not None:
            self.gesture_worker.stop()
            if not self.gesture_worker.wait(5000):
                event.ignore()
                self.statusBar().showMessage("Waiting for hand analysis to stop...")
                return
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
