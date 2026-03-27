"""
PyQt main interface for ArUco coordinate system
"""
import sys
from pathlib import Path
import cv2
import numpy as np
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QFileDialog,
                             QRadioButton, QButtonGroup, QTextEdit, QMessageBox, QSpinBox, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt5.QtGui import QImage, QPixmap, QMouseEvent
from aruco_core import ArUcoDetector, CoordinateTransformer, get_config
from aruco_core.run_logger import RunLogger, make_run_ts
from aruco_core.video_recorder import VideoRecorder


class ImageLabel(QLabel):
    """Custom QLabel for image display with mouse click handling"""

    clicked = pyqtSignal(int, int)  # Signal emitted when image is clicked (x, y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("border: 1px solid gray;")
        self.original_image = None
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0

    def set_image(self, image):
        """Set the image to display"""
        self.original_image = image.copy()
        self._update_display()

    def _update_display(self):
        """Update the displayed image"""
        if self.original_image is None:
            return

        # Convert BGR to RGB
        rgb_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w

        # Create QImage
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)

        # Scale to fit label while maintaining aspect ratio
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.setPixmap(scaled_pixmap)

        # Calculate scale factor and offset
        pixmap_rect = scaled_pixmap.rect()
        label_rect = self.rect()

        # Calculate scale factor (ratio between scaled and original)
        self.scale_factor_x = scaled_pixmap.width() / w
        self.scale_factor_y = scaled_pixmap.height() / h

        self.offset_x = (label_rect.width() - pixmap_rect.width()) // 2
        self.offset_y = (label_rect.height() - pixmap_rect.height()) // 2

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse click events"""
        if self.original_image is None:
            return

        # Get click position relative to label
        label_x = event.x()
        label_y = event.y()

        # Convert to image coordinates
        pixmap = self.pixmap()
        if pixmap is None:
            return

        pixmap_rect = pixmap.rect()
        pixmap_rect.moveTopLeft(
            QPoint(self.offset_x, self.offset_y)
        )

        if pixmap_rect.contains(label_x, label_y):
            # Calculate pixel coordinates in original image
            rel_x = label_x - self.offset_x
            rel_y = label_y - self.offset_y

            # Convert from scaled pixmap coordinates to original image coordinates
            img_x = int(rel_x / self.scale_factor_x)
            img_y = int(rel_y / self.scale_factor_y)

            # Emit signal with pixel coordinates
            self.clicked.emit(img_x, img_y)

    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self._update_display()


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArucoCalib")
        self.setGeometry(100, 100, 1200, 800)

        # Initialize components
        self.detector = ArUcoDetector()
        self.transformer = CoordinateTransformer()
        self.cfg = get_config()

        # Video capture
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.is_detecting = False

        # Session-level logging timestamp (created once per app run)
        self.script_start_ts = make_run_ts()
        repo_root = Path(__file__).resolve().parents[1]
        self.runs_root_dir = repo_root / "runs"
        self.run_logger = None

        # Raw video recording (mp4)
        self.is_recording = False
        self.video_recorder = None
        self.source_fps = 30.0

        # mp4 file path for "video detection" mode
        self.video_file_path = None

        # Current image
        self.current_image = None
        self.last_clicked_pixel = None
        self.last_clicked_world = None

        self.enable_trace = False
        # Trajectory history window (ms). Configure in config.yaml -> ui.trace_window_ms.
        self.trace_window_ms = int(getattr(self.cfg, "TRACE_WINDOW_MS", 500))
        self.trace_max_len = 15
        self.marker_traces = {}  # marker_id -> list[(x,y)]

        # Vehicle marker info (vehicle_id from config)
        self.vehicle_id = int(getattr(self.cfg, "VEHICLE_ID", 0))
        self.last_vehicle_center_px = None  # (cx, cy)
        self.last_vehicle_center_world = None  # (wx, wy) mm
        self.last_vehicle_yaw_deg = None  # float deg

        # Setup UI
        self.setup_ui()

    @staticmethod
    def _norm_angle_deg(a: float) -> float:
        """Normalize to (-180, 180]."""
        x = (float(a) + 180.0) % 360.0 - 180.0
        if x <= -180.0:
            x += 360.0
        return x

    def _update_vehicle_panel(self, detected: bool):
        vid = self.vehicle_id
        if not detected or self.last_vehicle_center_px is None:
            self.vehicle_text.setText(f"vehicle_id: {vid}\nStatus: Not detected")
            return

        cx, cy = self.last_vehicle_center_px
        lines = [f"vehicle_id: {vid}", f"center_px: ({cx:.1f}, {cy:.1f})"]

        if self.last_vehicle_center_world is None or self.last_vehicle_yaw_deg is None:
            lines.append("center_world(mm): Not calibrated")
            lines.append("yaw_deg: Not calibrated")
        else:
            wx, wy = self.last_vehicle_center_world
            lines.append(f"center_world(mm): ({wx:.2f}, {wy:.2f})")
            lines.append(f"yaw_deg: {self.last_vehicle_yaw_deg:.2f}")

        self.vehicle_text.setText("\n".join(lines))

    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # Left panel: Image display
        left_panel = QVBoxLayout()

        # Image display
        self.image_label = ImageLabel()
        self.image_label.clicked.connect(self.on_image_clicked)
        left_panel.addWidget(self.image_label)

        # Control buttons
        button_layout = QHBoxLayout()

        # Input source selection
        self.input_group = QButtonGroup()
        self.radio_image = QRadioButton("Image")
        self.radio_camera = QRadioButton("Camera")
        self.radio_video = QRadioButton("Video")
        self.radio_image.setChecked(True)
        self.input_group.addButton(self.radio_image, 0)
        self.input_group.addButton(self.radio_camera, 1)
        self.input_group.addButton(self.radio_video, 2)
        self.input_group.buttonClicked.connect(self.on_input_source_changed)

        button_layout.addWidget(self.radio_image)
        button_layout.addWidget(self.radio_camera)
        button_layout.addWidget(self.radio_video)

        self.btn_load_image = QPushButton("Load Image")
        self.btn_load_image.clicked.connect(self.load_image)
        button_layout.addWidget(self.btn_load_image)

        self.btn_choose_video = QPushButton("Select Video")
        self.btn_choose_video.clicked.connect(self.choose_video)
        self.btn_choose_video.setEnabled(False)
        button_layout.addWidget(self.btn_choose_video)

        self.btn_start = QPushButton("Start Detection")
        self.btn_start.clicked.connect(self.start_detection)
        button_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Detection")
        self.btn_stop.clicked.connect(self.stop_detection)
        self.btn_stop.setEnabled(False)
        button_layout.addWidget(self.btn_stop)

        self.btn_record_toggle = QPushButton("Start Recording")
        self.btn_record_toggle.clicked.connect(self.toggle_recording)
        self.btn_record_toggle.setEnabled(False)
        button_layout.addWidget(self.btn_record_toggle)

        left_panel.addLayout(button_layout)

        main_layout.addLayout(left_panel, 2)

        # Right panel: Information display
        right_panel = QVBoxLayout()

        # Status label
        self.status_label = QLabel("Status: Idle")
        right_panel.addWidget(self.status_label)

        # Coordinate display
        coord_label = QLabel("Coordinate Info:")
        right_panel.addWidget(coord_label)

        self.coord_text = QTextEdit()
        self.coord_text.setReadOnly(True)
        self.coord_text.setMaximumHeight(200)
        right_panel.addWidget(self.coord_text)

        # Vehicle status display (based on config.yaml vehicle_id)
        vehicle_label = QLabel("Vehicle Info (from vehicle_id):")
        right_panel.addWidget(vehicle_label)

        self.vehicle_text = QTextEdit()
        self.vehicle_text.setReadOnly(True)
        self.vehicle_text.setMaximumHeight(130)
        right_panel.addWidget(self.vehicle_text)

        # Tag status display (based on config.yaml world_coordinates)
        tag_label = QLabel("Tag Detection Status (from config.yaml):")
        right_panel.addWidget(tag_label)

        self.tag_status_text = QTextEdit()
        self.tag_status_text.setReadOnly(True)
        self.tag_status_text.setMaximumHeight(220)
        right_panel.addWidget(self.tag_status_text)

        # Calibration status
        self.calib_label = QLabel("Calibration: Not calibrated")
        right_panel.addWidget(self.calib_label)

        # Grid size setting (unit: mm in this project)
        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid Size (mm):"))
        self.grid_size_spin = QSpinBox()
        self.grid_size_spin.setRange(1, 5000)
        self.grid_size_spin.setValue(50)
        self.grid_size_spin.setSingleStep(10)
        self.grid_size_spin.valueChanged.connect(self.on_grid_size_changed)
        grid_row.addWidget(self.grid_size_spin)
        right_panel.addLayout(grid_row)

        self.chk_trace = QCheckBox("Show Trace")
        self.chk_trace.stateChanged.connect(self.on_trace_toggled)
        right_panel.addWidget(self.chk_trace)

        # Add stretch to push content to top
        right_panel.addStretch()

        main_layout.addLayout(right_panel, 1)

    def on_input_source_changed(self, button):
        """Handle input source change"""
        if button == self.radio_camera:
            self.btn_load_image.setEnabled(False)
            self.btn_choose_video.setEnabled(False)
            self.btn_record_toggle.setEnabled(True)

            self.stop_recording()
            if not self.is_detecting:
                self.stop_camera()
                self.start_camera()

        elif button == self.radio_video:
            self.btn_load_image.setEnabled(False)
            self.btn_choose_video.setEnabled(True)
            self.btn_record_toggle.setEnabled(False)

            self.stop_recording()
            self.stop_camera()
            if self.video_file_path is not None:
                self.start_video(self.video_file_path)

        else:
            # self.radio_image
            self.btn_load_image.setEnabled(True)
            self.btn_choose_video.setEnabled(False)
            self.btn_record_toggle.setEnabled(False)

            self.stop_recording()
            self.stop_camera()

    def on_grid_size_changed(self, value: int):
        """
        Update grid overlay when grid size changes.
        Only triggers a redraw for static-image mode to avoid extra computation on camera frames.
        """
        _ = value
        if self.current_image is None:
            return
        if self.radio_image.isChecked() and self.transformer.get_calibration_status():
            # Redetect markers so the overlay matches current frame.
            corners, ids, image_with_markers = self.detector.detect_markers(self.current_image)
            overlay_img = self.draw_grid_and_axes(image_with_markers)
            # Preserve the last clicked point (if any)
            if self.last_clicked_pixel is not None:
                x, y = self.last_clicked_pixel
                cv2.circle(overlay_img, (x, y), 5, (0, 255, 0), -1)
                cv2.circle(overlay_img, (x, y), 10, (0, 255, 0), 2)
            self.image_label.set_image(overlay_img)

    def on_trace_toggled(self, state: int):
        self.enable_trace = state == Qt.Checked
        if not self.enable_trace:
            self.marker_traces = {}

    def load_image(self):
        """Load image from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )

        if file_path:
            image = cv2.imread(file_path)
            if image is not None:
                self.current_image = image
                self.image_label.set_image(image)
                self.status_label.setText(f"Status: Image loaded - {file_path}")
                # Auto detect markers
                self.detect_and_calibrate(image)
            else:
                QMessageBox.warning(self, "Error", "Failed to load image file")

    def start_camera(self):
        """Start camera capture"""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            QMessageBox.warning(self, "Error", "Failed to open camera")
            self.radio_image.setChecked(True)
            return

        # Determine FPS for recording/video pacing.
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        try:
            fps = float(fps)
        except Exception:
            fps = 0.0
        if fps <= 0.0:
            fps = 30.0
        self.source_fps = fps

        self._update_trace_max_len()

        interval_ms = max(1, int(round(1000.0 / self.source_fps)))
        self.timer.start(interval_ms)
        self.status_label.setText(f"Status: Camera started (FPS={self.source_fps:.1f})")

    def stop_camera(self):
        """Stop current capture (camera/video)."""
        if self.cap is not None:
            self.timer.stop()
            self.cap.release()
            self.cap = None

        self.stop_recording()

        if self.radio_video.isChecked():
            self.status_label.setText("Status: Video stopped")
        elif self.radio_camera.isChecked():
            self.status_label.setText("Status: Camera stopped")
        else:
            self.status_label.setText("Status: Stopped")

    def start_video(self, file_path: str):
        """Start playing an mp4 (or other supported) file for detection."""
        self.cap = cv2.VideoCapture(file_path)
        if not self.cap.isOpened():
            QMessageBox.warning(self, "Error", f"Failed to open video file: {file_path}")
            self.radio_image.setChecked(True)
            self.video_file_path = None
            return

        fps = self.cap.get(cv2.CAP_PROP_FPS)
        try:
            fps = float(fps)
        except Exception:
            fps = 0.0
        if fps <= 0.0:
            fps = 30.0
        self.source_fps = fps

        self._update_trace_max_len()

        interval_ms = max(1, int(round(1000.0 / self.source_fps)))
        self.timer.start(interval_ms)
        self.status_label.setText(f"Status: Video started - {file_path} (FPS={self.source_fps:.1f})")

    def _update_trace_max_len(self):
        """Update trajectory max length from the desired time window and current FPS."""
        fps = float(self.source_fps) if self.source_fps else 30.0
        window_s = max(0.0, float(self.trace_window_ms) / 1000.0)
        # At least 2 points so a line can be drawn.
        self.trace_max_len = max(2, int(round(fps * window_s)))

    def choose_video(self):
        """Select an mp4 file for "video detection" mode."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)",
        )
        if not file_path:
            return

        self.video_file_path = file_path
        self.status_label.setText(f"Status: Video selected - {file_path}")

        if self.radio_video.isChecked():
            self.stop_camera()
            self.start_video(self.video_file_path)

    def stop_recording(self):
        """Stop mp4 recording if active."""
        if self.is_recording:
            self.is_recording = False
            if self.video_recorder is not None:
                self.video_recorder.stop()
            self.video_recorder = None
            self.btn_record_toggle.setText("Start Recording")
            # Keep status label intact if detection is running; otherwise set a neutral message.
            if not self.is_detecting:
                self.status_label.setText("Status: Recording stopped")

    def toggle_recording(self):
        """Toggle mp4 recording (raw frames only)."""
        if not self.radio_camera.isChecked():
            QMessageBox.information(self, "Info", "Recording is available only in camera mode")
            return

        if self.is_recording:
            self.stop_recording()
            return

        # Ensure capture is running so we can write the first frame soon.
        if self.cap is None:
            self.start_camera()

        record_start_ts = make_run_ts()
        record_dir = self.runs_root_dir / self.script_start_ts / "videos"
        mp4_path = record_dir / f"record_{record_start_ts}.mp4"
        self.video_recorder = VideoRecorder(mp4_path, fps=self.source_fps)
        self.is_recording = True
        self.btn_record_toggle.setText("Stop Recording")
        self.status_label.setText(f"Status: Recording -> {mp4_path.name}")

    def start_detection(self):
        """Start detection"""
        self.is_detecting = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        if self.radio_image.isChecked():
            if self.current_image is not None:
                self.detect_and_calibrate(self.current_image)
            return

        # Camera / video detection mode: ensure capture + run logger.
        if self.radio_camera.isChecked():
            if self.cap is None:
                self.start_camera()
        elif self.radio_video.isChecked():
            if self.video_file_path is None:
                QMessageBox.warning(self, "Error", "Please select a video file first")
                self.is_detecting = False
                self.btn_start.setEnabled(True)
                self.btn_stop.setEnabled(False)
                return
            if self.cap is None:
                self.start_video(self.video_file_path)

        if self.run_logger is None:
            self.run_logger = RunLogger(self.script_start_ts, runs_root_dir=self.runs_root_dir)

        self.status_label.setText("Status: Detection started (logging raw frames/timestamps)")

    def stop_detection(self):
        """Stop detection"""
        self.is_detecting = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        if self.radio_image.isChecked() and self.current_image is not None:
            # For static image mode, remove any overlay by showing raw image again.
            self.image_label.set_image(self.current_image)
        else:
            self.status_label.setText("Status: Detection stopped")

    def update_frame(self):
        """Update frame from camera"""
        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.current_image = frame

                # Optional raw frame recording (mp4), independent from inference.
                if self.is_recording and self.video_recorder is not None:
                    self.video_recorder.write_frame(frame)

                # Optional logging + inference.
                if self.is_detecting:
                    if self.run_logger is not None:
                        self.run_logger.save_frame(frame)
                    self.detect_and_calibrate(frame)
                else:
                    self.image_label.set_image(frame)
                return

            # End of stream (video file) or read error.
            self.timer.stop()
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

            if self.radio_video.isChecked():
                self.is_detecting = False
                self.btn_start.setEnabled(True)
                self.btn_stop.setEnabled(False)
                self.status_label.setText("Status: Video playback finished")
            else:
                self.status_label.setText("Status: Capture failed/stopped")

    def detect_and_calibrate(self, image):
        """Detect ArUco markers and calibrate coordinate system"""
        # Detect markers
        corners, ids, image_with_markers = self.detector.detect_markers(image)

        # Marker centers of all currently visible IDs
        all_marker_centers = self.detector.get_marker_centers(corners, ids)

        # Update tag status panel (show config-defined IDs and their current detection state)
        self.update_tag_status(all_marker_centers)

        # Required marker set for full homography re-calibration
        required_marker_centers = self.detector.get_required_markers(corners, ids)

        if required_marker_centers is not None:
            # Calibrate coordinate system
            success = self.transformer.calibrate(required_marker_centers)
            if success:
                self.calib_label.setText("Calibration: Calibrated")
                self.status_label.setText("Status: 4 markers detected, calibrated")
            else:
                self.calib_label.setText("Calibration: Failed")
                self.status_label.setText("Status: 4 markers detected, calibration failed")
                self.transformer.reset_calibration()
        else:
            detected_count = len(ids) if ids is not None else 0
            self.calib_label.setText("Calibration: Not calibrated")
            self.status_label.setText(
                f"Status: {detected_count} markers detected, 4 required for calibration"
            )
            # Hide grid until next full alignment.
            self.transformer.reset_calibration()

        # Vehicle marker (single ID) pose display (based on current calibration status)
        vehicle_detected = False
        self.last_vehicle_center_px = None
        self.last_vehicle_center_world = None
        self.last_vehicle_yaw_deg = None
        if ids is not None and corners is not None:
            flat_ids = ids.flatten()
            matches = np.where(flat_ids == int(self.vehicle_id))[0]
            if matches.size > 0:
                i = int(matches[0])
                try:
                    marker_corners_px = np.array(corners[i][0], dtype=np.float32)  # (4,2)
                    center_px = np.mean(marker_corners_px, axis=0)
                    cx, cy = float(center_px[0]), float(center_px[1])
                    self.last_vehicle_center_px = (cx, cy)
                    vehicle_detected = True

                    if self.transformer.get_calibration_status():
                        center_world = self.transformer.pixel_to_world(cx, cy, z=0.0)
                        # Heading direction: corner 1 -> corner 2
                        c1 = marker_corners_px[1]
                        c2 = marker_corners_px[2]
                        p1w = self.transformer.pixel_to_world(float(c1[0]), float(c1[1]), z=0.0)
                        p2w = self.transformer.pixel_to_world(float(c2[0]), float(c2[1]), z=0.0)
                        if center_world is not None and p1w is not None and p2w is not None:
                            dx = float(p2w[0] - p1w[0])
                            dy = float(p2w[1] - p1w[1])
                            yaw_deg = math.degrees(math.atan2(dy, dx))
                            self.last_vehicle_center_world = center_world
                            self.last_vehicle_yaw_deg = self._norm_angle_deg(yaw_deg)
                except Exception:
                    vehicle_detected = False

        self._update_vehicle_panel(vehicle_detected)

        # Display image with markers + overlay (only when calibrated)
        if self.transformer.get_calibration_status():
            image_with_markers = self.draw_grid_and_axes(image_with_markers)

        # Trajectory overlay (pixel space). Does not affect H calculation.
        if self.enable_trace and all_marker_centers:
            for mid, center in all_marker_centers.items():
                mid = int(mid)
                pt = (int(round(float(center[0]))), int(round(float(center[1]))))
                trace = self.marker_traces.get(mid, [])
                trace.append(pt)
                if len(trace) > self.trace_max_len:
                    trace = trace[-self.trace_max_len:]
                self.marker_traces[mid] = trace

                if len(trace) >= 2:
                    pts = np.array(trace, dtype=np.int32).reshape(-1, 1, 2)
                    cv2.polylines(
                        image_with_markers,
                        [pts],
                        isClosed=False,
                        color=(255, 0, 0),
                        thickness=2,
                    )

        # (Removed) YOLO overlay
        self.image_label.set_image(image_with_markers)

    def on_image_clicked(self, x, y):
        """Handle image click event"""
        if self.current_image is None:
            return

        # Check if coordinates are valid
        h, w = self.current_image.shape[:2]
        if x < 0 or x >= w or y < 0 or y >= h:
            return

        # Convert to world coordinates
        world_coords = self.transformer.pixel_to_world(x, y, z=0.0)
        self.last_clicked_pixel = (x, y)
        self.last_clicked_world = world_coords

        # Update coordinate display
        coord_info = f"Pixel coordinates: ({x}, {y})\n"
        if world_coords is not None:
            coord_info += f"World coordinates: ({world_coords[0]:.2f}, {world_coords[1]:.2f})\n"
        else:
            coord_info += "World coordinates: Not calibrated, conversion unavailable\n"

        self.coord_text.setText(coord_info)

        # Draw point on image
        image_copy = self.current_image.copy()
        cv2.circle(image_copy, (x, y), 5, (0, 255, 0), -1)
        cv2.circle(image_copy, (x, y), 10, (0, 255, 0), 2)

        # Re-detect markers to keep them visible
        corners, ids, image_with_markers = self.detector.detect_markers(image_copy)
        if self.transformer.get_calibration_status():
            image_with_markers = self.draw_grid_and_axes(image_with_markers)
        self.image_label.set_image(image_with_markers)

    def draw_grid_and_axes(self, image_bgr):
        """
        Draw world grid and X/Y axes on the given image using world->pixel mapping.

        World coordinate axes follow `config.WORLD_COORDINATES`:
        - x axis: along increasing world x (ID0 -> ID1)
        - y axis: along increasing world y
        """
        if not self.transformer.get_calibration_status():
            return image_bgr

        step_mm = int(self.grid_size_spin.value())
        margin_mm = step_mm
        # Draw minor grid at half spacing for more visual reference.
        step_minor_mm = max(0.5, step_mm / 2.0)

        # World coordinate drawing range (unit: mm).
        # Your request: -5m ~ 5m.
        range_mm = 5000.0
        x0 = -range_mm
        x1 = range_mm
        y0 = -range_mm
        y1 = range_mm

        # Use darker grid color so it remains visible on bright backgrounds,
        # especially after UI down-scaling.
        grid_color = (90, 90, 90)  # BGR
        minor_grid_color = (140, 140, 140)  # BGR (lighter than major)
        axis_x_color = (0, 0, 255)  # Red (BGR)
        axis_y_color = (0, 200, 0)  # Green (BGR)

        # Draw thickness in *original image space* so it stays visible after QLabel down-scaling.
        img_h, img_w = image_bgr.shape[:2]
        label_w = max(1, self.image_label.width())
        label_h = max(1, self.image_label.height())
        scale = min(label_w / float(img_w), label_h / float(img_h))
        if scale <= 0:
            scale = 1.0

        # Target thickness in display space (roughly in pixels).
        grid_thickness_display_px = 2.0
        axis_thickness_display_px = 4.0
        grid_thickness = max(1, int(round(grid_thickness_display_px / scale)))
        axis_thickness = max(grid_thickness + 1, int(round(axis_thickness_display_px / scale)))
        minor_grid_thickness = max(1, int(round(grid_thickness * 0.6)))

        # Helper to draw a line between two world points.
        def draw_world_line(wx1, wy1, wx2, wy2, color, thickness):
            p1 = self.transformer.world_to_pixel(wx1, wy1)
            p2 = self.transformer.world_to_pixel(wx2, wy2)
            if p1 is None or p2 is None:
                return
            # Draw the portion of the projected *infinite line* that intersects
            # the image rectangle. This avoids the issue where OpenCV may not
            # draw the segment when both endpoints are outside the image.
            x_min, y_min = 0.0, 0.0
            x_max, y_max = float(img_w - 1), float(img_h - 1)

            x1_, y1_ = float(p1[0]), float(p1[1])
            x2_, y2_ = float(p2[0]), float(p2[1])

            dx = x2_ - x1_
            dy = y2_ - y1_

            candidates = []

            def add_candidate(cx, cy):
                if cx < x_min - 1e-6 or cx > x_max + 1e-6:
                    return
                if cy < y_min - 1e-6 or cy > y_max + 1e-6:
                    return
                candidates.append((cx, cy))

            # Intersect with rectangle edges x = x_min/x_max and y = y_min/y_max.
            eps = 1e-12
            if abs(dx) > eps:
                # x = x_min
                t = (x_min - x1_) / dx
                cy = y1_ + t * dy
                add_candidate(x_min, cy)
                # x = x_max
                t = (x_max - x1_) / dx
                cy = y1_ + t * dy
                add_candidate(x_max, cy)
            if abs(dy) > eps:
                # y = y_min
                t = (y_min - y1_) / dy
                cx = x1_ + t * dx
                add_candidate(cx, y_min)
                # y = y_max
                t = (y_max - y1_) / dy
                cx = x1_ + t * dx
                add_candidate(cx, y_max)

            if len(candidates) < 2:
                return

            # Deduplicate very close points.
            unique = []
            tol = 1e-3
            for cx, cy in candidates:
                if all((cx - ux) ** 2 + (cy - uy) ** 2 > tol ** 2 for ux, uy in unique):
                    unique.append((cx, cy))

            if len(unique) < 2:
                return

            # Choose the two farthest points on the rectangle boundary.
            max_d = -1.0
            pA = None
            pB = None
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    ux, uy = unique[i]
                    vx, vy = unique[j]
                    d = (ux - vx) ** 2 + (uy - vy) ** 2
                    if d > max_d:
                        max_d = d
                        pA = unique[i]
                        pB = unique[j]

            if pA is None or pB is None:
                return

            cx1, cy1 = pA
            cx2, cy2 = pB

            cv2.line(
                image_bgr,
                (int(round(cx1)), int(round(cy1))),
                (int(round(cx2)), int(round(cy2))),
                color,
                thickness,
            )

        # Draw grid lines (minor first, then major so major stays prominent)
        # Minor grid
        start_x_minor = np.floor(x0 / step_minor_mm) * step_minor_mm
        end_x_minor = np.ceil(x1 / step_minor_mm) * step_minor_mm
        start_y_minor = np.floor(y0 / step_minor_mm) * step_minor_mm
        end_y_minor = np.ceil(y1 / step_minor_mm) * step_minor_mm

        for wx in np.arange(start_x_minor, end_x_minor + 0.5 * step_minor_mm, step_minor_mm):
            draw_world_line(wx, y0, wx, y1, minor_grid_color, minor_grid_thickness)
        for wy in np.arange(start_y_minor, end_y_minor + 0.5 * step_minor_mm, step_minor_mm):
            draw_world_line(x0, wy, x1, wy, minor_grid_color, minor_grid_thickness)

        # Major grid
        start_x = np.floor(x0 / step_mm) * step_mm
        end_x = np.ceil(x1 / step_mm) * step_mm
        start_y = np.floor(y0 / step_mm) * step_mm
        end_y = np.ceil(y1 / step_mm) * step_mm

        for wx in np.arange(start_x, end_x + 0.5 * step_mm, step_mm):
            draw_world_line(wx, y0, wx, y1, grid_color, grid_thickness)
        for wy in np.arange(start_y, end_y + 0.5 * step_mm, step_mm):
            draw_world_line(x0, wy, x1, wy, grid_color, grid_thickness)

        # Draw axes (x axis at world_y=0, y axis at world_x=0)
        draw_world_line(x0, 0.0, x1, 0.0, axis_x_color, axis_thickness)
        draw_world_line(0.0, y0, 0.0, y1, axis_y_color, axis_thickness)

        # Put axis labels near positive ends
        px_pos_x = self.transformer.world_to_pixel(x1, 0.0)
        py_pos_y = self.transformer.world_to_pixel(0.0, y1)
        font = cv2.FONT_HERSHEY_SIMPLEX
        if px_pos_x is not None:
            cv2.putText(
                image_bgr,
                "X",
                (int(round(px_pos_x[0])) + 5, int(round(px_pos_x[1])) - 5),
                font,
                0.7,
                axis_x_color,
                2,
                cv2.LINE_AA,
            )
        if py_pos_y is not None:
            cv2.putText(
                image_bgr,
                "Y",
                (int(round(py_pos_y[0])) + 5, int(round(py_pos_y[1])) + 15),
                font,
                0.7,
                axis_y_color,
                2,
                cv2.LINE_AA,
            )

        return image_bgr

    def update_tag_status(self, marker_centers):
        """
        Update right-panel tag status view.

        Args:
            marker_centers: dict[int, np.array([x,y], float32)] of current-frame centers
        """
        known_ids = sorted(self.cfg.WORLD_COORDINATES.keys())
        lines = []
        for mid in known_ids:
            if marker_centers is None or mid not in marker_centers:
                lines.append(f"ID {mid}: Not detected")
                continue
            c = marker_centers[mid]
            lines.append(f"ID {mid}: Detected center_px=({float(c[0]):.1f}, {float(c[1]):.1f})")

        self.tag_status_text.setText("\n".join(lines))

    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_camera()
        event.accept()


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

