"""Generate ``assets/BettyPet.ico`` from ``assets/stand.png``.

Crops the character to its alpha bounding box, pads to a square so the icon
is not stretched, and writes the standard Windows icon size ladder. Re-run
after changing the source art:

    python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]


def square_crop(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    return canvas


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = Image.open(root / "assets" / "stand.png").convert("RGBA")
    icon = square_crop(source).resize((256, 256), Image.Resampling.LANCZOS)
    target = root / "assets" / "BettyPet.ico"
    icon.save(target, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
