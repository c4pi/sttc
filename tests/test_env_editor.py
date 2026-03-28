from pathlib import Path

from sttc.gui.env_editor import upsert_env_values


def test_upsert_env_values_updates_existing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\nB=2\n# keep\n", encoding="utf-8")

    upsert_env_values({"B": "22", "C": True}, env_path=env_path)

    content = env_path.read_text(encoding="utf-8")
    assert "A=1" in content
    assert "B=22" in content
    assert "C=true" in content
    assert "# keep" in content


def test_upsert_env_values_creates_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    upsert_env_values({"ENABLE_GUI": False, "STT_CHUNK_SECONDS": 30}, env_path=env_path)

    content = env_path.read_text(encoding="utf-8")
    assert "ENABLE_GUI=false" in content
    assert "STT_CHUNK_SECONDS=30" in content
