# Changelog

This file tracks notable project changes over time.

## Unreleased

### Fixed

- Freestyle hotkey (`Ctrl+Alt+F`) is now visible and configurable in the Settings UI (Hotkeys tab).
  Previously the hotkey was fully wired in the backend but missing from all four relevant code paths
  in `settings_window.py` (field display, preview validation, runtime settings build, `.env` write).

---

## [v0.1.4] – 2026-06-02

### Added

- **Freestyle hotkey** (`Ctrl+Alt+F`): press the hotkey to snapshot the current clipboard, record a
  voice prompt, and send both as a combined request to the configured LLM — the result is written
  back to the clipboard. Useful for open-ended tasks like "reply to this email like a pirate."
- `FREESTYLE_HOTKEY` setting (default `ctrl+alt+f`) with conflict detection against all other
  hotkeys and documentation in both `.env.example` files.
- `process_freestyle()` function in `refiner.py` with a dedicated system prompt separating the
  voice instruction from the clipboard context.

---

## [v0.1.3] – 2026-04-10

### Added

- Clipboard-based refinement workflows for `refine`, `summary`, `translation`, and `record-and-refine`.
- A separate `REFINE_MODEL` setting for clipboard processing, alongside the existing transcription model settings.
- Clipboard read fallbacks so the app can process the current clipboard contents in place.

### Changed

- Declared the project as officially Windows-only in the README for now.
- Added dedicated hotkeys: `REFINE_HOTKEY`, `RECORD_AND_REFINE_HOTKEY`, `SUMMARY_HOTKEY`, `TRANSLATION_HOTKEY`.
- Updated the default `RECORD_AND_REFINE_HOTKEY` from `ctrl+alt+e` to `ctrl+alt+w`; existing `.env` files need a manual migration.
- Refinement hotkeys now require `OPENAI_API_KEY` and are silently disabled when it is missing.
- Disabled macOS and Linux release jobs in the GitHub Actions workflow (can be re-enabled by uncommenting the relevant steps).

### Notes

- Cross-platform runtime code is still present in the codebase.
- The CLI and GUI now warn when refinement hotkeys are unavailable because `OPENAI_API_KEY` is unset.

---

## [v0.1.2] – 2026-03-29

### Fixed

- Settings precedence: explicitly resolved `.env` file now takes priority over inherited shell
  environment variables so user config is not silently overridden.
- Various env-loading and settings-validation edge cases.

### Changed

- README corrections and minor copy improvements.
- Adjusted default keybindings to reduce conflicts with common system shortcuts.

---

## [v0.1.1] – 2026-03-28

### Added

- Full GUI (PySide6): system tray icon, settings window, mini overlay window with recording state.

### Fixed

- Windows release pipeline: hotfix for installer packaging and asset upload.

### Changed

- Removed committed build artefacts from the repository.
- Refactored audio resampling helper for clarity; removed unused code paths.

---

## [v0.1.0] – 2026-03-06

### Added

- PyInstaller-based bundled executables for Windows with auto-start support.
- GitHub Actions release workflow that builds and uploads the installer on version tags.
