"""
Make the web versions of the gallery photos.

    python scripts/gallery_images.py

For each images/gallery/gallery-N.(jpg|jpeg|png|webp), N = 1..4:
  - writes gallery-N-800.webp and gallery-N-1600.webp (never upscaled: if the
    photo is narrower than 1600px, the "1600" file keeps the original width);
  - turns phone photos the right way up (EXIF orientation);
  - removes hidden metadata (EXIF, e.g. GPS location of the phone) from the
    original file too, so it is safe to upload.

index.html already points to these file names, so after replacing a photo
you only run this command again. Needs Pillow (python -m pip install pillow).
"""
import sys
from pathlib import Path

from PIL import Image, ImageOps

GALLERY = Path(__file__).resolve().parent.parent / "images" / "gallery"
COUNT = 4
WIDTHS = (800, 1600)
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def find_original(n: int):
    for ext in EXTENSIONS:
        path = GALLERY / f"gallery-{n}{ext}"
        if path.exists():
            return path
    return None


def strip_metadata(path: Path, image: Image.Image) -> bool:
    """Re-save the original without EXIF if it has any. Returns True if it did."""
    if not image.getexif():
        return False
    clean = ImageOps.exif_transpose(image).convert("RGB")
    if path.suffix.lower() in (".jpg", ".jpeg"):
        clean.save(path, "JPEG", quality=95, optimize=True)
    elif path.suffix.lower() == ".webp":
        clean.save(path, "WEBP", quality=95)
    else:
        clean.save(path)
    return True


def main() -> int:
    if not GALLERY.is_dir():
        print(f"Folder not found: {GALLERY}")
        return 1
    missing = 0
    for n in range(1, COUNT + 1):
        original = find_original(n)
        if original is None:
            print(f"gallery-{n}: no photo found (gallery-{n}.jpg) - skipped")
            missing += 1
            continue
        with Image.open(original) as raw:
            raw.load()
            image = ImageOps.exif_transpose(raw).convert("RGB")
            stripped = strip_metadata(original, raw)
        notes = []
        for target in WIDTHS:
            width = min(target, image.width)
            height = round(image.height * width / image.width)
            resized = image.resize((width, height), Image.LANCZOS) if width != image.width else image
            out = GALLERY / f"gallery-{n}-{target}.webp"
            resized.save(out, "WEBP", quality=80, method=6)
            notes.append(f"{out.name} {width}x{height} {out.stat().st_size // 1024} KB")
        extra = " (metadata removed from original)" if stripped else ""
        print(f"gallery-{n}: {original.name} {image.width}x{image.height}{extra}")
        for note in notes:
            print(f"    {note}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
