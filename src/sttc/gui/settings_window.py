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
    QVBoxLayout,
    QWidget,
)

from sttc.autostart import disable_autostart, enable_autostart, is_autostart_enabled
from sttc.gui.env_editor import upsert_env_values
from sttc.settings import Settings, get_settings

if TYPE_CHECKING:
    from sttc.gui.bridge import STTCBridge


class SettingsWindow(QDialog):
    """Dialog for editing runtime and startup settings."""

    def __init__(self, bridge: STTCBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._autostart_enabled = is_autostart_enabled()

        self.setWindowTitle("STTC Settings")
        self.resize(680, 500)

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

    def _build_transcription_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.stt_model_input = QLineEdit(settings.stt_model or "")
        self.stt_model_input.setPlaceholderText("Leave empty for local faster-whisper")

        self.stt_whisper_model_input = QLineEdit(settings.stt_whisper_model)
        self.openai_api_key_input = QLineEdit(settings.openai_api_key or "")
        self.openai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.model_cache_input = QLineEdit(settings.stt_model_cache_dir or "")
        self.model_cache_input.setPlaceholderText("Optional custom model cache directory")

        form.addRow("Cloud Model (STT_MODEL)", self.stt_model_input)
        form.addRow("Whisper Model", self.stt_whisper_model_input)
        form.addRow("API Key", self.openai_api_key_input)
        form.addRow("Model Cache Dir", self.model_cache_input)

        hint = QLabel("Leave Cloud Model empty to use local faster-whisper.")
        form.addRow("", hint)
        return tab

    def _build_hotkeys_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.recording_mode_combo = QComboBox()
        self.recording_mode_combo.addItems(["toggle", "hold"])
        self.recording_mode_combo.setCurrentText(settings.recording_mode)

        self.recording_hotkey_input = QLineEdit(settings.recording_hotkey)
        self.quit_hotkey_input = QLineEdit(settings.quit_hotkey)

        form.addRow("Recording Mode", self.recording_mode_combo)
        form.addRow("Recording Hotkey", self.recording_hotkey_input)
        form.addRow("Quit Hotkey", self.quit_hotkey_input)
        return tab

    def _build_startup_tab(self, settings: Settings) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.enable_gui_checkbox = QCheckBox("Enable GUI by default")
        self.enable_gui_checkbox.setChecked(settings.enable_gui)

        self.gui_start_minimized_checkbox = QCheckBox("Start GUI minimized")
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

        self.sample_rate_input = QSpinBox()
        self.sample_rate_input.setRange(8000, 96000)
        self.sample_rate_input.setSingleStep(1000)
        self.sample_rate_input.setValue(settings.sample_rate_target)

        self.channels_input = QSpinBox()
        self.channels_input.setRange(1, 2)
        self.channels_input.setValue(settings.channels)

        grid.addWidget(QLabel("Chunk Seconds"), 0, 0)
        grid.addWidget(self.chunk_seconds_input, 0, 1)
        grid.addWidget(QLabel("Sample Rate"), 1, 0)
        grid.addWidget(self.sample_rate_input, 1, 1)
        grid.addWidget(QLabel("Channels"), 2, 0)
        grid.addWidget(self.channels_input, 2, 1)
        grid.setColumnStretch(2, 1)
        return tab

    def _build_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch(1)

        save_button = QPushButton("Save")
        save_button.clicked.connect(lambda: self._save(restart_engine=False))

        save_restart_button = QPushButton("Save + Restart Engine")
        save_restart_button.clicked.connect(lambda: self._save(restart_engine=True))

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(save_button)
        layout.addWidget(save_restart_button)
        layout.addWidget(cancel_button)
        return layout

    @staticmethod
    def _normalize_hotkey(value: str) -> str:
        return value.strip().lower().replace(" ", "")

    def _collect_updates(self) -> dict[str, bool | int | str | None]:
        return {
            "STT_MODEL": self.stt_model_input.text().strip(),
            "STT_WHISPER_MODEL": self.stt_whisper_model_input.text().strip() or "base",
            "OPENAI_API_KEY": self.openai_api_key_input.text().strip(),
            "STT_MODEL_CACHE_DIR": self.model_cache_input.text().strip(),
            "RECORDING_MODE": self.recording_mode_combo.currentText(),
            "RECORDING_HOTKEY": self._normalize_hotkey(self.recording_hotkey_input.text()),
            "QUIT_HOTKEY": self._normalize_hotkey(self.quit_hotkey_input.text()),
            "ENABLE_GUI": self.enable_gui_checkbox.isChecked(),
            "GUI_START_MINIMIZED": self.gui_start_minimized_checkbox.isChecked(),
            "STT_CHUNK_SECONDS": self.chunk_seconds_input.value(),
            "SAMPLE_RATE_TARGET": self.sample_rate_input.value(),
            "CHANNELS": self.channels_input.value(),
        }

    def _validate_updates(self) -> tuple[bool, str]:
        recording_mode = self.recording_mode_combo.currentText()
        if recording_mode not in {"toggle", "hold"}:
            return False, "Recording mode must be either 'toggle' or 'hold'."

        try:
            Settings(
                stt_model=self.stt_model_input.text().strip() or None,
                stt_whisper_model=self.stt_whisper_model_input.text().strip() or "base",
                openai_api_key=self.openai_api_key_input.text().strip() or None,
                stt_model_cache_dir=self.model_cache_input.text().strip() or None,
                recording_mode=cast('Literal["hold", "toggle"]', recording_mode),
                recording_hotkey=self._normalize_hotkey(self.recording_hotkey_input.text()),
                quit_hotkey=self._normalize_hotkey(self.quit_hotkey_input.text()),
                enable_gui=self.enable_gui_checkbox.isChecked(),
                gui_start_minimized=self.gui_start_minimized_checkbox.isChecked(),
                stt_chunk_seconds=self.chunk_seconds_input.value(),
                sample_rate_target=self.sample_rate_input.value(),
                channels=self.channels_input.value(),
            )
        except Exception as exc:
            return False, str(exc)
        return True, ""

    def _save(self, *, restart_engine: bool) -> None:
        updates = self._collect_updates()
        valid, message = self._validate_updates()
        if not valid:
            QMessageBox.warning(self, "Invalid Settings", message)
            return

        env_path = upsert_env_values(updates)

        wanted_autostart = self.autostart_checkbox.isChecked()
        if wanted_autostart != self._autostart_enabled:
            if wanted_autostart:
                enable_autostart(gui=bool(updates["ENABLE_GUI"]), minimized=bool(updates["GUI_START_MINIMIZED"]))
            else:
                disable_autostart()
            self._autostart_enabled = wanted_autostart

        new_settings = get_settings()
        self._bridge.apply_settings(new_settings, restart=restart_engine)

        QMessageBox.information(self, "Settings Saved", f"Settings saved to {env_path}")
        self.accept()
