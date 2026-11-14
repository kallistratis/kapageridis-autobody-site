"""
Copy ONLY the files the site needs online into one folder you can upload
(for example: drag the folder into https://app.netlify.com/drop).

    python scripts/export_site.py          ->  _upload/kapageridis-site   (the real site, kapageridis.gr)
    python scripts/export_site.py --demo   ->  _upload/kapageridis-demo   (preview link, hidden from Google)

How it works: it starts from every page (index.html, 404.html, <folder>/index.html),
follows every local file those pages and their CSS use (src, href, srcset, poster,
url(), @import, and https://kapageridis.gr/... addresses in meta tags and schema) and
copies just those, plus robots.txt and sitemap.xml. Source files stay out: scripts,
data, templates, design notes, component previews, original JPG photos.
Run `python scripts/build.py` first, so the pages are up to date.

--demo: every page gets <meta name="robots" content="noindex, nofollow"> and a
Netlify "_headers" file says the same, so Google does not list the temporary link
before the real kapageridis.gr.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
OUT_BASE = ROOT / "_upload"
SITE_URL = "https://kapageridis.gr"
SKIP_DIRS = {"design-system", "scripts", "data", "templates", ".claude", ".git", "node_modules", "_upload"}
ALWAYS = ["robots.txt", "sitemap.xml"]
NOT_LOCAL = ("http://", "https://", "//", "mailto:", "tel:", "viber:", "data:", "javascript:", "#")

ATTR_RE = re.compile(r'\b(?:src|href|poster)="([^"]+)"')
SRCSET_RE = re.compile(r'\bsrcset="([^"]+)"')
SITE_RE = re.compile(re.escape(SITE_URL) + r'(/[^"\s<>\\]*)')
CSS_URL_RE = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)|@import\s+[\'"]([^\'"]+)[\'"]')
ROBOTS_META_RE = re.compile(r'<meta name="robots" content="[^"]*">')


def pages() -> list[Path]:
    found = []
    for path in ROOT.rglob("*.html"):
        rel = path.relative_to(ROOT)
        if SKIP_DIRS & set(rel.parts[:-1]):
            continue
        if len(rel.parts) == 1 or path.name == "index.html":
            found.append(path)
    return sorted(found)


def resolve(url: str, base: Path) -> Path | None:
    """Local file for a link/asset URL, or None for external links, anchors, phone links…"""
    url = url.strip()
    if not url or url.startswith(NOT_LOCAL):
        return None
    path = unquote(urlsplit(url).path)
    if not path:
        return None
    target = ROOT / path.lstrip("/") if path.startswith("/") else base.parent / path
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target.resolve()


def refs_in_html(text: str) -> list[str]:
    urls = ATTR_RE.findall(text)
    for srcset in SRCSET_RE.findall(text):
        urls += [part.strip().split(" ")[0] for part in srcset.split(",") if part.strip()]
    urls += SITE_RE.findall(text)  # og:image, schema logo, canonical…
    return urls


def refs_in_css(text: str) -> list[str]:
    return [a or b for a, b in CSS_URL_RE.findall(text)]


def collect() -> tuple[set[Path], list[str]]:
    keep: set[Path] = set()
    missing: list[str] = []
    todo = [p.resolve() for p in pages()] + [(ROOT / name).resolve() for name in ALWAYS]
    while todo:
        file = todo.pop()
        if file in keep:
            continue
        if not file.is_file():
            missing.append(str(file.relative_to(ROOT)))
            continue
        if ROOT.resolve() not in file.parents:
            continue
        keep.add(file)
        if file.suffix == ".html":
            urls = refs_in_html(file.read_text(encoding="utf-8"))
        elif file.suffix == ".css":
            urls = refs_in_css(file.read_text(encoding="utf-8"))
        else:
            continue
        for url in urls:
            target = resolve(url, file)
            if target is not None and target not in keep:
                todo.append(target)
    # the font licence goes wherever the fonts go
    licence = (ROOT / "design-system" / "fonts" / "OFL.txt").resolve()
    if licence.is_file() and any(p.suffix == ".woff2" for p in keep):
        keep.add(licence)
    return keep, sorted(set(missing))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--demo", action="store_true", help="preview copy: noindex on every page")
    args = parser.parse_args()

    out = OUT_BASE / ("kapageridis-demo" if args.demo else "kapageridis-site")
    if out.exists():
        shutil.rmtree(out)  # always inside _upload/, rebuilt from scratch every time

    keep, missing = collect()
    total = 0
    for src in sorted(keep):
        dest = out / src.relative_to(ROOT.resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.demo and src.suffix == ".html":
            html = src.read_text(encoding="utf-8")
            robots = '<meta name="robots" content="noindex, nofollow">'
            html = ROBOTS_META_RE.sub(robots, html) if ROBOTS_META_RE.search(html) else html.replace("<head>", f"<head>\n  {robots}", 1)
            dest.write_text(html, encoding="utf-8", newline="\n")
        else:
            shutil.copy2(src, dest)
        total += src.stat().st_size
    if args.demo:
        (out / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8")

    print(f"{len(keep)} files, {total / 1_048_576:.1f} MB -> {out}")
    print("pages: " + ", ".join(str(p.relative_to(ROOT)).replace("\\", "/") for p in pages()))
    if missing:
        print("MISSING (linked but not found):")
        for m in missing:
            print("  - " + m.replace("\\", "/"))
        sys.exit(1)


if __name__ == "__main__":
    main()
