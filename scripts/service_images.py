"""
Make the web versions of the service photos.

    python scripts/service_images.py

For each images/services/<name>.(jpg|jpeg|png|webp) listed in data/services.json
("image" field, and "homeImage" for the big home page panels): writes
<name>-800.webp and <name>-1600.webp (cards, panels, page hero),
never upscaled, turned the right way up, without hidden metadata (EXIF/GPS),
and records their sizes in data/service-images.json for the width/height
attributes. Then run: python scripts/build.py
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "images" / "services"
WIDTHS = (800, 1600)
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def main() -> int:
    services = json.loads((ROOT / "data" / "services.json").read_text(encoding="utf-8"))["services"]
    sizes = {}
    missing = 0
    names = [n for s in services for n in (s.get("image"), s.get("homeImage")) if n]
    for name in names:
        original = next((FOLDER / f"{name}{ext}" for ext in EXTENSIONS if (FOLDER / f"{name}{ext}").exists()), None)
        if original is None:
            print(f"{name}: no photo yet (images/services/{name}.jpg) - the card shows a grey box")
            missing += 1
            continue
        with Image.open(original) as raw:
            raw.load()
            image = ImageOps.exif_transpose(raw).convert("RGB")
            if raw.getexif():
                image.save(original, "JPEG" if original.suffix.lower() in (".jpg", ".jpeg") else None, quality=95)
        sizes[name] = {}
        for target in WIDTHS:
            width = min(target, image.width)
            height = round(image.height * width / image.width)
            out = FOLDER / f"{name}-{target}.webp"
            (image if width == image.width else image.resize((width, height), Image.LANCZOS)).save(
                out, "WEBP", quality=80, method=6
            )
            sizes[name][str(target)] = [width, height]
            print(f"{out.name} {width}x{height} {out.stat().st_size // 1024} KB")
    (ROOT / "data" / "service-images.json").write_text(json.dumps(sizes, indent=2), encoding="utf-8")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
