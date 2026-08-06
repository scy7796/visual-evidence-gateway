"""Generate a probe image with known but runtime-variable ground truth."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    # Pillow >=10.4 ships a scalable default font, avoiding host-specific font
    # paths that would make the probe unreadable or non-portable.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - compatibility fallback
        return ImageFont.load_default()


def generate(
    path,
    token: str = "VISION_PROBE_7319",
    *,
    red_count: int = 1,
    blue_count: int = 2,
) -> Path:
    if not 1 <= red_count <= 4 or not 1 <= blue_count <= 4:
        raise ValueError("probe shape counts must be between 1 and 4")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (760, 520), "white")
    draw = ImageDraw.Draw(img)
    draw.text((24, 20), token, fill="black", font=_font(42))

    for index in range(red_count):
        x = 48 + index * 165
        draw.ellipse((x, 150, x + 100, 250), fill="red", outline="red")
    for index in range(blue_count):
        x = 48 + index * 165
        draw.rectangle((x, 350, x + 100, 450), fill="blue", outline="blue")

    img.save(path, "PNG")
    return path


def main() -> int:
    import tempfile

    out = Path(tempfile.gettempdir()) / "visual-evidence-gateway" / "vision-probe.png"
    generate(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
