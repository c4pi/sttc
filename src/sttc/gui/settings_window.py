"""Expanded settings UI for configuring STTC."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sttc.autostart import is_autostart_enabled, sync_autostart
from sttc.gui.env_editor import upsert_env_values
from sttc.onboarding import CURATED_WHISPER_MODELS, DEFAULT_CLOUD_MODEL, normalize_hotkey
from sttc.settings import WHISPER_SAMPLE_RATE, Settings

if TYPE_CHECKING:
    from sttc.gui.bridge import STTCBridge


class SettingsWindow(QDialog):
    """Dialog for editing runtime and startup settings."""

    def __init__(self, bridge: STTCBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._autostart_enabled = is_autostart_enabled()

        self.setWindowTitle("STTC Settings")
        self.resize(680, 540)

        settings = bridge.get_settings()

        root_layout = QVBoxLayout()
        tabs = QTabWidget()

        tabs.addTab(self._build_transcription_tab(settings), "Transcription")
        tabs.addTab(self._build_hotkeys_tab(settings), "Hotkeys")
        tabs.addTab(self._build_startup_tab(settings), "Startup")
        tabs.addTab(self._build_advanced_tab(settings), "Advanced")

        root_layout.addWidget(tabs)
        root_layout.addLayout(self._build_buttons())
        self.setLayout(root_layout)
        self._sync_transcription_mode_controls()
        self._update_refinement_warning()

    def _build_transcription_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Cloud / OpenAI", userData="cloud")
        self.backend_combo.addItem("Local Whisper", userData="local")
        self.backend_combo.setCurrentIndex(0 if settings.stt_model else 1)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)

        self.stt_model_input = QLineEdit(settings.stt_model or DEFAULT_CLOUD_MODEL)
        self.stt_model_input.setPlaceholderText(DEFAULT_CLOUD_MODEL)

        self.refine_model_input = QLineEdit(settings.refine_model)
        self.refine_model_input.setPlaceholderText("gpt-4.1-mini")

        self.stt_whisper_model_input = QComboBox()
        self.stt_whisper_model_input.addItems(CURATED_WHISPER_MODELS)
        whisper_model = settings.stt_whisper_model or "base"
        if whisper_model not in CURATED_WHISPER_MODELS:
            self.stt_whisper_model_input.addItem(whisper_model)
        self.stt_whisper_model_input.setCurrentText(whisper_model)

        self.openai_api_key_input = QLineEdit(settings.openai_api_key or "")
        self.openai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_api_key_input.textChanged.connect(self._update_refinement_warning)
        self.api_key_toggle_button = QToolButton()
        self.api_key_toggle_button.setCheckable(True)
        self.api_key_toggle_button.setText("Show")
        self.api_key_toggle_button.toggled.connect(self._toggle_api_key_visibility)

        api_key_widget = QWidget()
        api_key_layout = QHBoxLayout(api_key_widget)
        api_key_layout.setContentsMargins(0, 0, 0, 0)
        api_key_layout.addWidget(self.openai_api_key_input, 1)
        api_key_layout.addWidget(self.api_key_toggle_button)

        self.model_cache_input = QLineEdit(settings.stt_model_cache_dir or "")
        self.model_cache_input.setPlaceholderText("Optional custom model cache directory")

        form.addRow("Backend", self.backend_combo)
        form.addRow("Cloud Model (STT_MODEL)", self.stt_model_input)
        form.addRow("Refine Model (REFINE_MODEL)", self.refine_model_input)
        form.addRow("Whisper Model", self.stt_whisper_model_input)
        form.addRow("API Key", api_key_widget)
        form.addRow("Model Cache Dir", self.model_cache_input)

        self.transcription_hint = QLabel("")
        self.transcription_hint.setWordWrap(True)
        form.addRow("", self.transcription_hint)

        self.refinement_warning = QLabel("")
        self.refinement_warning.setWordWrap(True)
        self.refinement_warning.setStyleSheet("color: #b00020;")
        form.addRow("", self.refinement_warning)
        self._sync_transcription_mode_controls()
        return tab

    def _build_hotkeys_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.recording_mode_combo = QComboBox()
        self.recording_mode_combo.addItems(["toggle", "hold"])
        self.recording_mode_combo.setCurrentText(settings.recording_mode)

        self.recording_hotkey_input = QLineEdit(settings.recording_hotkey)
        self.refine_hotkey_input = QLineEdit(settings.refine_hotkey)
        self.record_and_refine_hotkey_input = QLineEdit(settings.record_and_refine_hotkey)
        self.summary_hotkey_input = QLineEdit(settings.summary_hotkey)
        self.translation_hotkey_input = QLineEdit(settings.translation_hotkey)
        self.quit_hotkey_input = QLineEdit(settings.quit_hotkey)

        form.addRow("Recording Mode", self.recording_mode_combo)
        form.addRow("Recording Hotkey", self.recording_hotkey_input)
        form.addRow("Refine Hotkey", self.refine_hotkey_input)
        form.addRow("Record & Refine Hotkey", self.record_and_refine_hotkey_input)
        form.addRow("Summary Hotkey", self.summary_hotkey_input)
        form.addRow("Translation Hotkey", self.translation_hotkey_input)
        form.addRow("Quit Hotkey", self.quit_hotkey_input)
        return tab

    def _build_startup_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.enable_gui_checkbox = QCheckBox("Launch GUI on auto-start")
        self.enable_gui_checkbox.setChecked(settings.enable_gui)

        self.gui_start_minimized_checkbox = QCheckBox("Start auto-started GUI minimized")
        self.gui_start_minimized_checkbox.setChecked(settings.gui_start_minimized)

        self.autostart_checkbox = QCheckBox("Enable auto-start on login")
        self.autostart_checkbox.setChecked(self._autostart_enabled)

        layout.addWidget(self.enable_gui_checkbox)
        layout.addWidget(self.gui_start_minimized_checkbox)
        layout.addWidget(self.autostart_checkbox)
        layout.addStretch(1)
        return tab

    def _build_advanced_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)

        self.chunk_seconds_input = QSpinBox()
        self.chunk_seconds_input.setRange(1, 120)
        self.chunk_seconds_input.setValue(settings.stt_chunk_seconds)

        self.channels_input = QSpinBox()
        self.channels_input.setRange(1, 2)
        self.channels_input.setValue(settings.channels)

        grid.addWidget(QLabel("Chunk Seconds"), 0, 0)
        grid.addWidget(self.chunk_seconds_input, 0, 1)
        grid.addWidget(QLabel("Channels"), 1, 0)
        grid.addWidget(self.channels_input, 1, 1)

        sample_rate_hint = QLabel(
            f"Whisper sample rate is fixed to {WHISPER_SAMPLE_RATE} Hz. "
            "Recording still uses your audio device input rate (often 44100 Hz)."
        )
        sample_rate_hint.setWordWrap(True)
        grid.addWidget(sample_rate_hint, 2, 0, 1, 3)

        grid.setColumnStretch(2, 1)
        return tab

    def _build_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch(1)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(save_button)
        layout.addWidget(cancel_button)
        return layout

    def _on_backend_changed(self, _index: int) -> None:
        self._sync_transcription_mode_controls()

    def _toggle_api_key_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.openai_api_key_input.setEchoMode(mode)
        self.api_key_toggle_button.setText("Hide" if visible else "Show")

    def _uses_cloud_backend(self) -> bool:
        return self.backend_combo.currentData() == "cloud"

    def _selected_stt_model(self) -> str | None:
        if not self._uses_cloud_backend():
            return None
        return self.stt_model_input.text().strip() or DEFAULT_CLOUD_MODEL

    def _current_preview_settings(self) -> Settings:
        base_values = self._bridge.get_settings().model_dump()
        base_values.update(
            {
                "openai_api_key": self.openai_api_key_input.text().strip() or None,
                "refine_hotkey": normalize_hotkey(self.refine_hotkey_input.text()),
                "record_and_refine_hotkey": normalize_hotkey(self.record_and_refine_hotkey_input.text()),
                "summary_hotkey": normalize_hotkey(self.summary_hotkey_input.text()),
                "translation_hotkey": normalize_hotkey(self.translation_hotkey_input.text()),
            }
        )
        return Settings(**base_values)

    def _update_refinement_warning(self) -> None:
        try:
            preview_settings = self._current_preview_settings()
        except Exception:
            self.refinement_warning.setText("")
            return

        if preview_settings.refinement_hotkeys_enabled:
            self.refinement_warning.setText("")
            return

        line1, line2 = preview_settings.refinement_warning_lines
        self.refinement_warning.setText(f"{line1}\n{line2}")

    def _sync_transcription_mode_controls(self) -> None:
        uses_cloud = self._uses_cloud_backend()
        self.stt_model_input.setEnabled(uses_cloud)
        self.stt_whisper_model_input.setEnabled(not uses_cloud)
        if uses_cloud:
            self.transcription_hint.setText(
                "Cloud mode uses STT_MODEL for transcription. Refine, summary, and translation use OPENAI_API_KEY + REFINE_MODEL."
            )
        else:
            self.transcription_hint.setText(
                "Local mode uses Whisper Model for transcription. Refine, summary, and translation still use OPENAI_API_KEY + REFINE_MODEL."
            )

    def _build_runtime_settings(self) -> Settings:
        recording_mode = self.recording_mode_combo.currentText()
        base_values = self._bridge.get_settings().model_dump()
        base_values.update(
            {
                "stt_model": self._selected_stt_model(),
                "refine_model": self.refine_model_input.text().strip() or "gpt-4.1-mini",
                "stt_whisper_model": self.stt_whisper_model_input.currentText().strip() or "base",
                "openai_api_key": self.openai_api_key_input.text().strip() or None,
                "stt_model_cache_dir": self.model_cache_input.text().strip() or None,
                "recording_mode": cast('Literal["hold", "toggle"]', recording_mode),
                "recording_hotkey": normalize_hotkey(self.recording_hotkey_input.text()),
                "refine_hotkey": normalize_hotkey(self.refine_hotkey_input.text()),
                "record_and_refine_hotkey": normalize_hotkey(self.record_and_refine_hotkey_input.text()),
                "summary_hotkey": normalize_hotkey(self.summary_hotkey_input.text()),
                "translation_hotkey": normalize_hotkey(self.translation_hotkey_input.text()),
                "quit_hotkey": normalize_hotkey(self.quit_hotkey_input.text()),
                "enable_gui": self.enable_gui_checkbox.isChecked(),
                "gui_start_minimized": self.gui_start_minimized_checkbox.isChecked(),
                "stt_chunk_seconds": self.chunk_seconds_input.value(),
                "sample_rate_target": WHISPER_SAMPLE_RATE,
                "channels": self.channels_input.value(),
            }
        )
        return Settings(**base_values)

    def _collect_updates(self) -> dict[str, bool | int | str | None]:
        stt_model = ""
        selected_model = self._selected_stt_model()
        if selected_model is not None:
            stt_model = selected_model

        return {
            "STT_MODEL": stt_model,
            "REFINE_MODEL": self.refine_model_input.text().strip() or "gpt-4.1-mini",
            "STT_WHISPER_MODEL": self.stt_whisper_model_input.currentText().strip() or "base",
            "OPENAI_API_KEY": self.openai_api_key_input.text().strip(),
            "STT_MODEL_CACHE_DIR": self.model_cache_input.text().strip(),
            "RECORDING_MODE": self.recording_mode_combo.currentText(),
            "RECORDING_HOTKEY": normalize_hotkey(self.recording_hotkey_input.text()),
            "REFINE_HOTKEY": normalize_hotkey(self.refine_hotkey_input.text()),
            "RECORD_AND_REFINE_HOTKEY": normalize_hotkey(self.record_and_refine_hotkey_input.text()),
            "SUMMARY_HOTKEY": normalize_hotkey(self.summary_hotkey_input.text()),
            "TRANSLATION_HOTKEY": normalize_hotkey(self.translation_hotkey_input.text()),
            "QUIT_HOTKEY": normalize_hotkey(self.quit_hotkey_input.text()),
            "ENABLE_GUI": self.enable_gui_checkbox.isChecked(),
            "GUI_START_MINIMIZED": self.gui_start_minimized_checkbox.isChecked(),
            "STT_CHUNK_SECONDS": self.chunk_seconds_input.value(),
            "SAMPLE_RATE_TARGET": WHISPER_SAMPLE_RATE,
            "CHANNELS": self.channels_input.value(),
        }

    def _validate_updates(self) -> tuple[bool, str]:
        recording_mode = self.recording_mode_combo.currentText()
        if recording_mode not in {"toggle", "hold"}:
            return False, "Recording mode must be either 'toggle' or 'hold'."

        try:
            self._build_runtime_settings()
        except Exception as exc:
            return False, str(exc)
        return True, ""

    def _save(self) -> None:
        updates = self._collect_updates()
        valid, message = self._validate_updates()
        if not valid:
            QMessageBox.warning(self, "Invalid Settings", message)
            return

        env_path = upsert_env_values(updates)

        wanted_autostart = self.autostart_checkbox.isChecked()
        if wanted_autostart or self._autostart_enabled:
            sync_autostart(
                wanted_autostart,
                gui=bool(updates["ENABLE_GUI"]),
                minimized=bool(updates["GUI_START_MINIMIZED"]),
            )
        self._autostart_enabled = wanted_autostart

        new_settings = self._build_runtime_settings()
        try:
            self._bridge.apply_settings(new_settings, restart=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Engine Restart Failed",
                f"Settings were saved to {env_path}, but restarting the engine failed:\n{exc}",
            )
            return

        QMessageBox.information(self, "Settings Saved", f"Settings saved to {env_path}")
        self.accept()
