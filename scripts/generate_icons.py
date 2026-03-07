"""Generate simple GUI icon assets for STTC."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_DIR = PROJECT_ROOT / "src" / "sttc" / "gui" / "resources"


def _draw_circle_icon(path: Path, color: str, size: int = 64) -> None:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = int(size * 0.12)
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color)
    image.save(path)


def _draw_app_icon(path: Path, size: int = 256) -> None:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.ellipse((16, 16, size - 16, size - 16), fill="#0f172a")
    stem_left = int(size * 0.42)
    stem_right = int(size * 0.58)
    draw.rounded_rectangle((stem_left, int(size * 0.30), stem_right, int(size * 0.62)), radius=24, fill="white")
    draw.rectangle((int(size * 0.49), int(size * 0.62), int(size * 0.51), int(size * 0.78)), fill="white")
    draw.arc((int(size * 0.35), int(size * 0.62), int(size * 0.65), int(size * 0.90)), start=200, end=340, fill="white", width=8)
    image.save(path)


def main() -> None:
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    _draw_circle_icon(RESOURCES_DIR / "icon_idle.png", "#6b7280")
    _draw_circle_icon(RESOURCES_DIR / "icon_recording.png", "#e11d48")
    _draw_circle_icon(RESOURCES_DIR / "icon_transcribing.png", "#f59e0b")
    _draw_app_icon(RESOURCES_DIR / "app_icon.png")


if __name__ == "__main__":
    main()
