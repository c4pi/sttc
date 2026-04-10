# Changelog

This file tracks notable project changes over time.

## Unreleased

### Added

- Clipboard-based refinement workflows for `refine`, `summary`, `translation`, and `record-and-refine`.
- A separate `REFINE_MODEL` setting for clipboard processing, alongside the existing transcription model settings.
- Clipboard read fallbacks so the app can process the current clipboard contents in place.

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
