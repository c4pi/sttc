# Changelog

This file tracks notable project changes over time.

## Unreleased

### Added

- **Freestyle hotkey (`Ctrl+Alt+F`):** Records a voice prompt, combines it with the current clipboard content, and sends both to an LLM. The result replaces the clipboard. Configurable via `FREESTYLE_HOTKEY` in `.env`.
- **Modifier-state synchronization:** The hotkey listener now re-syncs modifier key state (Ctrl, Alt, Shift) against the real OS key state on every key event using `GetAsyncKeyState` on Windows. Handing stuck modifiers are healed automatically on the next keypress.
- **Trigger-on-non-modifier:** Hotkeys (including Quit) now only fire when the non-modifier key of the combo is the key that was just pressed. This prevents a single `q` press from triggering `Ctrl+Alt+Q` when modifiers were stuck from a previous Alt+Tab or focus switch.
- New helpers in `src/sttc/recorder.py`: `default_modifier_probe()`, `sync_modifier_state()`, `is_combo_trigger()`.
- `RuntimeController` uses the same modifier probe for all aux-hotkeys (refine, summary, translation, record-and-refine, freestyle).
- Clipboard-based refinement workflows for `refine`, `summary`, `translation`, and `record-and-refine`.
- A separate `REFINE_MODEL` setting for clipboard processing, alongside the existing transcription model settings.
- Clipboard read fallbacks so the app can process the current clipboard contents in place.

### Fixed

- **Silent exit / phantom quit bug:** App would occasionally quit on its own after Alt+Tab or a focus switch. Root cause: modifier key-up events are dropped by the Windows low-level keyboard hook when the window manager handles them (e.g. during Alt+Tab, UAC prompts, lock screen). Stuck `Ctrl`/`Alt` entries in `pressed_keys` meant that typing any `q` later matched the quit combo. Fixed by the modifier-state synchronization described above.
- Phantom recordings and unintended clipboard actions caused by the same stuck-modifier issue.

### Changed

- Declared the project as officially Windows-only in the README for now.
- Added dedicated hotkeys for `REFINE_HOTKEY`, `RECORD_AND_REFINE_HOTKEY`, `SUMMARY_HOTKEY`, and `TRANSLATION_HOTKEY`.
- Updated the default `RECORD_AND_REFINE_HOTKEY` from `ctrl+alt+e` to `ctrl+alt+w`; existing `.env` files need a manual migration.
- Refinement hotkeys now require `OPENAI_API_KEY` and are disabled automatically when it is missing.
- Disabled macOS and Linux release jobs in `.github/workflows/release.yml` by commenting them out so they can be restored later.

### Notes

- Cross-platform runtime code is still present in the codebase.
- The CLI and GUI now warn when refinement hotkeys are unavailable because `OPENAI_API_KEY` is unset.
- Re-enable non-Windows release steps later by uncommenting the relevant workflow sections.
- The modifier probe is injectable; in unit tests it is disabled so that real `GetAsyncKeyState` calls don't interfere with synthetic key events on Windows CI.
