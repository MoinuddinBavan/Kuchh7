"""3D capture and optional external image rendering review workspace."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..rendering import (STYLES, RenderRequest, capture_view_png,
                         configured_image_provider, save_png)


class _RenderWorker(QObject):
    finished = Signal(bytes)
    failed = Signal(str)

    def __init__(self, provider, request: RenderRequest) -> None:
        super().__init__()
        self.provider = provider
        self.request = request

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.provider.render(self.request))
        except Exception as error:
            self.failed.emit(str(error))


class RealisticRenderWorkspace(QWidget):
    def __init__(self, view3d, project_fingerprint_callback=None, capture_callback=None, parent=None) -> None:
        super().__init__(parent)
        self.view3d = view3d
        self._project_fingerprint_callback = project_fingerprint_callback
        self._capture_callback = capture_callback or (lambda camera: capture_view_png(view3d, camera))
        self._captured_fingerprint: str | None = None
        self.source_png: bytes | None = None
        self.result_png: bytes | None = None
        self._thread: QThread | None = None
        self._worker: _RenderWorker | None = None
        outer = QVBoxLayout(self)
        title = QLabel("REALISTIC RENDERING")
        title.setObjectName("canvasTitle")
        outer.addWidget(title)
        note = QLabel("Source is a standard 3D capture. An AI image may differ from the actual design and is never manufacturing accurate.")
        note.setWordWrap(True)
        outer.addWidget(note)
        options = QFormLayout()
        self.camera_combo = QComboBox()
        self.camera_combo.addItems(("Current", "Front", "Isometric", "Presentation"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(STYLES)
        self.instructions = QPlainTextEdit()
        self.instructions.setPlaceholderText("Optional visual instructions for an approved image provider")
        self.instructions.setMaximumHeight(68)
        options.addRow("Camera", self.camera_combo)
        options.addRow("Rendering style", self.style_combo)
        options.addRow("Presentation instructions", self.instructions)
        outer.addLayout(options)
        controls = QHBoxLayout()
        self.capture_button = QPushButton("Capture current 3D")
        self.capture_button.clicked.connect(self.capture)
        self.generate_button = QPushButton("Generate AI render")
        self.generate_button.setStyleSheet(
            "QPushButton:disabled { color: #829098; background: #E4E9EC; border-color: #CAD3D8; }"
        )
        self.generate_button.clicked.connect(self.generate)
        self.save_button = QPushButton("Save displayed image…")
        self.save_button.clicked.connect(self.save_image)
        self.save_button.setEnabled(False)
        controls.addWidget(self.capture_button)
        controls.addWidget(self.generate_button)
        controls.addWidget(self.save_button)
        controls.addStretch()
        outer.addLayout(controls)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        comparison = QSplitter(Qt.Orientation.Horizontal)
        self.before_label = QLabel("Capture the current 3D scene to see the source image.")
        self.after_label = QLabel("AI rendering unavailable until an approved provider is configured.")
        for caption, image_label in (("ORIGINAL 3D CAPTURE", self.before_label),
                                     ("OPTIONAL AI PRESENTATION IMAGE", self.after_label)):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            heading = QLabel(caption)
            heading.setObjectName("canvasTitle")
            panel_layout.addWidget(heading)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.setWordWrap(True)
            image_label.setMinimumSize(330, 250)
            image_label.setStyleSheet("background: #E8EDF0; border: 1px solid #C9D3D9; color: #425765;")
            panel_layout.addWidget(image_label, 1)
            comparison.addWidget(panel)
        comparison.setSizes([600, 600])
        outer.addWidget(comparison, 1)
        self.refresh_provider_status()

    @property
    def render_in_progress(self) -> bool:
        return self._thread is not None

    def refresh_provider_status(self, *, preserve_message: bool = False) -> None:
        try:
            provider = configured_image_provider()
        except ValueError as error:
            provider = None
            if not preserve_message:
                self.status_label.setText(f"Provider configuration invalid: {error}")
        else:
            if not preserve_message:
                self.status_label.setText(
                    f"{provider.name} ready. External image upload requires confirmation and may incur charges."
                    if provider else "No live AI provider configured. 3D capture and PNG saving are available."
                )
        self.generate_button.setEnabled(provider is not None and self.source_png is not None and self._thread is None)

    def _show_image(self, label: QLabel, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "PNG"):
            raise ValueError("Could not display the PNG image.")
        label.setProperty("sourcePixmap", pixmap)
        label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for label in (self.before_label, self.after_label):
            pixmap = label.property("sourcePixmap")
            if isinstance(pixmap, QPixmap):
                label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))

    def capture(self) -> bool:
        if self._thread is not None:
            return False
        self.status_label.setText("Capturing the actual 3D scene…")
        try:
            self.source_png = self._capture_callback(self.camera_combo.currentText())
            self._captured_fingerprint = (
                self._project_fingerprint_callback() if self._project_fingerprint_callback else None
            )
            self.result_png = None
            self._show_image(self.before_label, self.source_png)
            self.after_label.clear()
            self.after_label.setText("No AI image generated. Original 3D capture is ready to save.")
            self.after_label.setProperty("sourcePixmap", None)
            self.save_button.setEnabled(True)
            self.status_label.setText("Standard 3D capture ready. Project data unchanged.")
            self.refresh_provider_status()
            return True
        except Exception as error:
            self.source_png = None
            self.result_png = None
            self._captured_fingerprint = None
            self.generate_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.status_label.setText(f"3D capture failed: {error}")
            return False

    def generate(self) -> bool:
        if self._thread is not None or self.source_png is None:
            return False
        if (self._project_fingerprint_callback and self._captured_fingerprint
                != self._project_fingerprint_callback()):
            self.status_label.setText("Project changed since capture. Capture the current 3D scene again.")
            return False
        try:
            provider = configured_image_provider()
            if provider is None:
                self.refresh_provider_status()
                return False
            request = RenderRequest(self.source_png, self.style_combo.currentText(),
                                    self.instructions.toPlainText().strip())
            request.validate()
        except ValueError as error:
            self.status_label.setText(str(error))
            return False
        answer = QMessageBox.question(
            self, "Send design image to external provider?",
            f"This sends the current 3D capture and your presentation instructions to {provider.name}. "
            "The image may reveal a client layout and the request may incur charges. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status_label.setText("External rendering cancelled; image not uploaded.")
            return False
        self._thread = QThread(self)
        self._worker = _RenderWorker(provider, request)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._render_done)
        self._worker.failed.connect(self._render_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker_cleared)
        self.generate_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self.status_label.setText(f"{provider.name} is rendering… You can continue using the application.")
        self._thread.start()
        return True

    @Slot(bytes)
    def _render_done(self, data: bytes) -> None:
        self.result_png = data
        self._show_image(self.after_label, data)
        self.save_button.setEnabled(True)
        stale = (self._project_fingerprint_callback and self._captured_fingerprint
                 != self._project_fingerprint_callback())
        self.status_label.setText(
            "AI image is from an earlier project state; capture again for the current design."
            if stale else "AI presentation image ready. Verify it against the actual design before sharing."
        )

    @Slot(str)
    def _render_failed(self, message: str) -> None:
        self.status_label.setText(message)

    @Slot()
    def _worker_cleared(self) -> None:
        self._worker = None
        self._thread = None
        self.capture_button.setEnabled(True)
        self.refresh_provider_status(preserve_message=True)

    def save_image(self) -> bool:
        data = self.result_png or self.source_png
        if data is None:
            return False
        path, _filter = QFileDialog.getSaveFileName(self, "Save presentation PNG", "kuchhe7-3d-capture.png", "PNG image (*.png)")
        if not path:
            return False
        try:
            save_png(data, path)
        except (OSError, ValueError) as error:
            self.status_label.setText(f"Could not save image: {error}")
            return False
        self.status_label.setText(f"Saved {'AI presentation image' if self.result_png else 'standard 3D capture'} to {path}")
        return True
