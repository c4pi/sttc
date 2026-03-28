"""Dedicated onboarding dialog for first launch and manual setup."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sttc.onboarding import (
    CURATED_WHISPER_MODELS,
    DEFAULT_CLOUD_MODEL,
    Backend,
    OnboardingValues,
    RecordingMode,
    default_onboarding_values,
    persist_onboarding_values,
)
from sttc.transcriber import should_announce_model_download, validate_openai_api_key

if TYPE_CHECKING:
    from sttc.settings import Settings


class OnboardingDialog(QDialog):
    """Short first-run flow that saves the core STTC setup choices."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_settings = settings
        self._saved_settings: Settings | None = None
        self._defaults = default_onboarding_values(settings)

        self.setWindowTitle("Welcome to STTC")
        self.resize(640, 520)
        self.setModal(True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        root_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel()
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet("color: #475569;")
        root_layout.addWidget(self._subtitle_label)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_welcome_page())
        self._stack.addWidget(self._build_backend_page())
        self._stack.addWidget(self._build_hotkeys_page())
        self._stack.addWidget(self._build_review_page())
        root_layout.addWidget(self._stack, 1)

        button_row = QHBoxLayout()
        self._back_button = QPushButton("Back")
        self._back_button.clicked.connect(self._go_back)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.reject)
        self._next_button = QPushButton("Next")
        self._next_button.clicked.connect(self._go_next)
        self._finish_button = QPushButton("Finish")
        self._finish_button.clicked.connect(self._finish)

        button_row.addWidget(self._back_button)
        button_row.addStretch(1)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._next_button)
        button_row.addWidget(self._finish_button)
        root_layout.addLayout(button_row)

        self._backend_combo.currentIndexChanged.connect(self._sync_backend_controls)
        self._api_key_toggle.toggled.connect(self._toggle_api_key_visibility)

        self._apply_defaults()
        self._refresh_step()

    def saved_settings(self) -> Settings | None:
        return self._saved_settings

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        intro = QLabel(
            "STTC can run fully local with Whisper or use OpenAI cloud transcription. "
            "This setup flow keeps the first launch short and only asks for the settings that matter most now."
        )
        intro.setWordWrap(True)

        details = QLabel(
            "Default hotkeys:\n"
            f"  Start/stop recording: {self._defaults.recording_hotkey}\n"
            f"  Quit STTC: {self._defaults.quit_hotkey}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        recommended = QPushButton("Use Recommended Defaults")
        recommended.clicked.connect(self._use_recommended_defaults)

        note = QLabel(
            "Recommended defaults use local Whisper with the base model, toggle recording, and no auto-start."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #475569;")

        layout.addWidget(intro)
        layout.addWidget(details)
        layout.addWidget(recommended, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_backend_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._backend_combo = QComboBox()
        self._backend_combo.addItem("Local Whisper", userData="local")
        self._backend_combo.addItem("Cloud / OpenAI", userData="cloud")

        self._whisper_model_combo = QComboBox()
        self._whisper_model_combo.addItems(CURATED_WHISPER_MODELS)

        self._cloud_model_input = QLineEdit()
        self._cloud_model_input.setPlaceholderText(DEFAULT_CLOUD_MODEL)

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_toggle = QToolButton()
        self._api_key_toggle.setCheckable(True)
        self._api_key_toggle.setText("Show")

        api_key_row = QWidget()
        api_key_layout = QHBoxLayout(api_key_row)
        api_key_layout.setContentsMargins(0, 0, 0, 0)
        api_key_layout.addWidget(self._api_key_input, 1)
        api_key_layout.addWidget(self._api_key_toggle)

        self._backend_hint = QLabel()
        self._backend_hint.setWordWrap(True)
        self._backend_hint.setStyleSheet("color: #475569;")

        form.addRow("Backend", self._backend_combo)
        form.addRow("Whisper model", self._whisper_model_combo)
        form.addRow("Cloud model", self._cloud_model_input)
        form.addRow("OpenAI API key", api_key_row)
        form.addRow("", self._backend_hint)
        return page

    def _build_hotkeys_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._recording_mode_combo = QComboBox()
        self._recording_mode_combo.addItems(["toggle", "hold"])

        self._recording_hotkey_input = QLineEdit()
        self._quit_hotkey_input = QLineEdit()

        self._autostart_checkbox = QCheckBox("Start STTC automatically when you log in")
        self._enable_gui_checkbox = QCheckBox("Launch GUI when auto-start runs")
        self._start_minimized_checkbox = QCheckBox("Start the auto-started GUI minimized")

        form.addRow("Recording mode", self._recording_mode_combo)
        form.addRow("Recording hotkey", self._recording_hotkey_input)
        form.addRow("Quit hotkey", self._quit_hotkey_input)
        form.addRow("", self._autostart_checkbox)
        form.addRow("", self._enable_gui_checkbox)
        form.addRow("", self._start_minimized_checkbox)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        summary_hint = QLabel(
            "Review the setup. If you finish with Local Whisper and the model is not cached yet, STTC will start the download next."
        )
        summary_hint.setWordWrap(True)

        self._review_text = QTextEdit()
        self._review_text.setReadOnly(True)

        layout.addWidget(summary_hint)
        layout.addWidget(self._review_text, 1)
        return page

    def _apply_defaults(self) -> None:
        self._backend_combo.setCurrentIndex(0 if self._defaults.backend == "local" else 1)
        self._whisper_model_combo.setCurrentText(self._defaults.whisper_model)
        self._cloud_model_input.setText(self._defaults.cloud_model)
        self._api_key_input.setText(self._defaults.openai_api_key)
        self._recording_mode_combo.setCurrentText(self._defaults.recording_mode)
        self._recording_hotkey_input.setText(self._defaults.recording_hotkey)
        self._quit_hotkey_input.setText(self._defaults.quit_hotkey)
        self._autostart_checkbox.setChecked(self._defaults.autostart_enabled)
        self._enable_gui_checkbox.setChecked(self._defaults.enable_gui)
        self._start_minimized_checkbox.setChecked(self._defaults.gui_start_minimized)
        self._sync_backend_controls()

    def _use_recommended_defaults(self) -> None:
        self._backend_combo.setCurrentIndex(0)
        self._whisper_model_combo.setCurrentText("base")
        self._cloud_model_input.setText(DEFAULT_CLOUD_MODEL)
        self._api_key_input.clear()
        self._recording_mode_combo.setCurrentText("toggle")
        self._recording_hotkey_input.setText("ctrl+alt+a")
        self._quit_hotkey_input.setText("ctrl+alt+q")
        self._autostart_checkbox.setChecked(False)
        self._enable_gui_checkbox.setChecked(self._defaults.enable_gui)
        self._start_minimized_checkbox.setChecked(False)
        self._stack.setCurrentIndex(3)
        self._refresh_step()

    def _refresh_step(self) -> None:
        index = self._stack.currentIndex()
        step_titles = [
            ("Welcome", "A quick overview before STTC starts doing any work."),
            ("Transcription Backend", "Choose local Whisper or cloud transcription and fill in the matching model settings."),
            ("Hotkeys and Startup", "Confirm the recording mode, hotkeys, and what auto-start should launch."),
            ("Review and Finish", "Save these choices. STTC will only start the engine after this step is complete."),
        ]
        title, subtitle = step_titles[index]
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)
        self._back_button.setVisible(index > 0)
        self._next_button.setVisible(index < self._stack.count() - 1)
        self._finish_button.setVisible(index == self._stack.count() - 1)
        if index == self._stack.count() - 1:
            self._update_review()
            self._finish_button.setText(self._finish_button_label())

    def _sync_backend_controls(self) -> None:
        uses_cloud = self._backend_combo.currentData() == "cloud"
        self._whisper_model_combo.setEnabled(not uses_cloud)
        self._cloud_model_input.setEnabled(uses_cloud)
        self._api_key_input.setEnabled(uses_cloud)
        self._api_key_toggle.setEnabled(uses_cloud)
        if not uses_cloud and self._api_key_toggle.isChecked():
            self._api_key_toggle.setChecked(False)
        self._backend_hint.setText(
            "Cloud mode needs a model name and API key. Local Whisper downloads a model after setup finishes if it is not cached yet."
            if uses_cloud
            else "Local mode keeps audio on your machine. The first start may download the selected Whisper model."
        )

    def _toggle_api_key_visibility(self, visible: bool) -> None:
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self._api_key_toggle.setText("Hide" if visible else "Show")

    def _go_back(self) -> None:
        self._stack.setCurrentIndex(max(0, self._stack.currentIndex() - 1))
        self._refresh_step()

    def _go_next(self) -> None:
        self._stack.setCurrentIndex(min(self._stack.count() - 1, self._stack.currentIndex() + 1))
        self._refresh_step()

    def _current_values(self) -> OnboardingValues:
        return OnboardingValues(
            backend=cast("Backend", self._backend_combo.currentData()),
            cloud_model=self._cloud_model_input.text().strip() or DEFAULT_CLOUD_MODEL,
            openai_api_key=self._api_key_input.text().strip(),
            whisper_model=self._whisper_model_combo.currentText(),
            recording_mode=cast("RecordingMode", self._recording_mode_combo.currentText()),
            recording_hotkey=self._recording_hotkey_input.text(),
            quit_hotkey=self._quit_hotkey_input.text(),
            autostart_enabled=self._autostart_checkbox.isChecked(),
            enable_gui=self._enable_gui_checkbox.isChecked(),
            gui_start_minimized=self._start_minimized_checkbox.isChecked(),
        )

    def _try_build_settings(self, values: OnboardingValues) -> Settings | None:
        if values.backend == "cloud" and not values.openai_api_key.strip():
            return None
        try:
            return values.to_settings(self._base_settings)
        except Exception:
            return None

    def _validate_values(self, values: OnboardingValues) -> Settings | None:
        if values.backend == "cloud" and not values.openai_api_key.strip():
            QMessageBox.warning(self, "Missing API Key", "Cloud transcription needs an OpenAI API key.")
            return None
        if values.backend == "cloud":
            try:
                validate_openai_api_key(values.openai_api_key)
            except RuntimeError as exc:
                QMessageBox.warning(self, "Invalid API Key", str(exc))
                return None
        try:
            return values.to_settings(self._base_settings)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Settings", str(exc))
            return None

    def _update_review(self) -> None:
        values = self._current_values()
        lines = [
            "STTC setup summary",
            "",
            f"Backend: {'Cloud / OpenAI' if values.backend == 'cloud' else 'Local Whisper'}",
        ]
        if values.backend == "cloud":
            lines.extend(
                [
                    f"Cloud model: {values.cloud_model}",
                    "API key: configured" if values.openai_api_key.strip() else "API key: missing",
                ]
            )
        else:
            lines.append(f"Whisper model: {values.whisper_model}")
        lines.extend(
            [
                f"Recording mode: {values.recording_mode}",
                f"Recording hotkey: {values.recording_hotkey}",
                f"Quit hotkey: {values.quit_hotkey}",
                f"Auto-start: {'enabled' if values.autostart_enabled else 'disabled'}",
                f"Auto-start launch: {'GUI' if values.enable_gui else 'CLI / headless'}",
                f"Start minimized: {'yes' if values.gui_start_minimized else 'no'}",
            ]
        )
        self._review_text.setPlainText("\n".join(lines))

    def _finish_button_label(self) -> str:
        values = self._current_values()
        settings = self._try_build_settings(values)
        if settings is None:
            return "Finish"
        if values.backend == "local" and should_announce_model_download(settings):
            return "Finish and Download Model"
        return "Finish"

    def _finish(self) -> None:
        values = self._current_values()
        validated_settings = self._validate_values(values)
        if validated_settings is None:
            return

        new_settings, env_path = persist_onboarding_values(self._base_settings, values)
        self._saved_settings = new_settings
        message = f"Settings saved to {env_path}"
        if values.backend == "local" and should_announce_model_download(validated_settings):
            message += "\n\nThe Whisper model download will start next."
        QMessageBox.information(self, "STTC Setup Complete", message)
        self.accept()
