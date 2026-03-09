"""First-launch setup for bundled executables."""

from __future__ import annotations

from getpass import getpass
import importlib
import os
import sys
from urllib import error as urllib_error
from urllib import request as urllib_request

from sttc.autostart import enable_autostart, is_autostart_enabled
from sttc.settings import Settings, ensure_bundled_env_file, get_user_config_dir, is_bundled_executable

FIRST_RUN_MARKER = ".first_run_complete"
AUTOSTART_ENV_KEY = "AUTO_START_ENABLED"
API_KEY_ENV_KEY = "OPENAI_API_KEY"  # pragma: allowlist secret
DEFAULT_CLOUD_MODEL = "openai/gpt-4o-mini-transcribe"


def ensure_local_model_available(settings: Settings, *, announce: bool) -> None:
    ensure_local_model_available_impl = importlib.import_module("sttc.transcriber").ensure_local_model_available
    ensure_local_model_available_impl(settings, announce=announce)


def _marker_path(config_dir):
    return config_dir / FIRST_RUN_MARKER


def _has_interactive_stdin() -> bool:
    stdin = sys.stdin
    if stdin is None or stdin.closed:
        return False
    try:
        stdin.read(0)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def _ask_yes_no(prompt: str) -> bool | None:
    while True:
        try:
            response = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt, RuntimeError):
            print("No choice captured. STTC will ask again on next launch.", flush=True)
            return None

        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False

        print("Please answer with 'y' or 'n'.", flush=True)


def _validate_openai_api_key(api_key: str) -> tuple[bool, str]:
    req = urllib_request.Request(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "sttc-setup",
        },
        method="GET",
    )

    try:
        with urllib_request.urlopen(req, timeout=8) as response:  # noqa: S310
            if response.status == 200:
                return True, "ok"
            return False, f"OpenAI returned status {response.status}."
    except urllib_error.HTTPError as exc:
        if exc.code in {401, 403}:
            return False, "API key rejected by OpenAI (unauthorized)."
        return False, f"OpenAI request failed with status {exc.code}."
    except urllib_error.URLError as exc:
        return False, f"Could not reach OpenAI ({exc.reason})."


def _ask_api_key() -> str | None:
    while True:
        try:
            value = getpass("Enter your API key (or type 'skip'): ").strip()
        except (EOFError, KeyboardInterrupt, RuntimeError):
            print("No API key captured. STTC will ask again on next launch.", flush=True)
            return None

        if value.lower() == "skip":
            return ""

        if not value:
            print("API key cannot be empty. Enter a key or type 'skip'.", flush=True)
            continue

        valid, reason = _validate_openai_api_key(value)
        if valid:
            print("API key verified.", flush=True)
            return value

        print(f"Invalid API key: {reason}", flush=True)
        print("Provide a valid key or type 'skip' to continue with local Whisper.", flush=True)


def _upsert_env_var(env_path, key: str, value: str) -> None:
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    assignment = f"{key}={value}"
    found = False
    updated_lines: list[str] = []

    for line in lines:
        if line.startswith(f"{key}="):
            updated_lines.append(assignment)
            found = True
        else:
            updated_lines.append(line)

    if not found:
        updated_lines.append(assignment)

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _write_first_run_marker(marker_path, *, autostart_enabled: bool, cloud_enabled: bool) -> None:
    autostart_state = "enabled" if autostart_enabled else "disabled"
    cloud_state = "enabled" if cloud_enabled else "disabled"
    marker_path.write_text(
        f"autostart={autostart_state}\ncloud_transcription={cloud_state}\n",
        encoding="utf-8",
    )


def _complete_noninteractive_first_run(settings: Settings, *, env_path, marker_path) -> None:
    autostart_enabled = is_autostart_enabled()
    cloud_enabled = bool(settings.openai_api_key and settings.stt_model)
    _upsert_env_var(env_path, AUTOSTART_ENV_KEY, "true" if autostart_enabled else "false")
    _write_first_run_marker(
        marker_path,
        autostart_enabled=autostart_enabled,
        cloud_enabled=cloud_enabled,
    )


def run_first_launch_setup(settings: Settings) -> None:
    """Run first-launch setup; no-op for development execution."""
    if not is_bundled_executable():
        return

    config_dir = get_user_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    marker_path = _marker_path(config_dir)

    env_path, created = ensure_bundled_env_file()
    if created:
        print(f"Created initial configuration at {env_path}", flush=True)

    if marker_path.exists():
        return

    if not _has_interactive_stdin():
        _complete_noninteractive_first_run(settings, env_path=env_path, marker_path=marker_path)
        return

    autostart_enabled = is_autostart_enabled()
    if not autostart_enabled:
        autostart_choice = _ask_yes_no("Enable STTC auto-start on login? [y/n]: ")
        if autostart_choice is None:
            if not _has_interactive_stdin():
                _complete_noninteractive_first_run(settings, env_path=env_path, marker_path=marker_path)
            return

        if autostart_choice:
            enable_autostart()
            autostart_enabled = True
            print("Auto-start enabled.", flush=True)
            print("You can disable later with: sttc.exe autostart disable", flush=True)
        else:
            print("Auto-start remains disabled.", flush=True)
            print("You can enable later with: sttc.exe autostart enable", flush=True)
    else:
        print("Auto-start is already enabled.", flush=True)
        print("You can disable later with: sttc.exe autostart disable", flush=True)

    _upsert_env_var(env_path, AUTOSTART_ENV_KEY, "true" if autostart_enabled else "false")

    has_api_key = _ask_yes_no("Do you have an AI API key now (for cloud transcription)? [y/n]: ")
    if has_api_key is None:
        if not _has_interactive_stdin():
            _complete_noninteractive_first_run(settings, env_path=env_path, marker_path=marker_path)
        return

    cloud_enabled = False
    if has_api_key:
        api_key = _ask_api_key()
        if api_key is None:
            if not _has_interactive_stdin():
                _complete_noninteractive_first_run(settings, env_path=env_path, marker_path=marker_path)
            return

        if api_key:
            _upsert_env_var(env_path, API_KEY_ENV_KEY, api_key)
            _upsert_env_var(env_path, "STT_MODEL", DEFAULT_CLOUD_MODEL)
            os.environ[API_KEY_ENV_KEY] = api_key
            settings.openai_api_key = api_key
            settings.stt_model = DEFAULT_CLOUD_MODEL
            cloud_enabled = True
            print(
                f"Cloud transcription enabled with model: {DEFAULT_CLOUD_MODEL}",
                flush=True,
            )
        else:
            _upsert_env_var(env_path, "STT_MODEL", "")
            settings.stt_model = None
    else:
        _upsert_env_var(env_path, "STT_MODEL", "")
        settings.stt_model = None

    if not cloud_enabled:
        print("No API key configured. STTC will use local Whisper transcription.", flush=True)
        print("Downloading speech model... (one-time setup)", flush=True)
        ensure_local_model_available(settings, announce=False)
        print(
            "You can add an API key later in your .env file and set STT_MODEL to a cloud model.",
            flush=True,
        )

    print(f"Configuration file: {env_path}", flush=True)
    print("You can check auto-start status with: sttc.exe autostart status", flush=True)

    _write_first_run_marker(
        marker_path,
        autostart_enabled=autostart_enabled,
        cloud_enabled=cloud_enabled,
    )
