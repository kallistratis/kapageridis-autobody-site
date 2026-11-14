"""
Make the looping background video of a service page hero.

    python scripts/service_videos.py <name> <source.mp4> [--start S] [--end E]
                                     [--loop crossfade|pingpong] [--fade 1.0]

Writes (no sound, small enough for the web):
  assets/video/service-<name>.mp4          computers, up to 1920 px wide
  assets/video/service-<name>-mobile.mp4   phones (portrait), 960 px wide
  images/services/<name>-poster.webp       first frame: shown until the video plays,
                                           and instead of it with "reduce motion"

The browser restarts the video when it ends. To hide that jump:
  crossfade  the last second fades into the first one (use it when people move)
  pingpong   plays forward, then backwards (slow camera moves: no jump at all)

Needs ffmpeg: on PATH, in the FFMPEG environment variable, or from the
imageio-ffmpeg Python package. Afterwards add "heroVideo": "<name>" to the
service in data/services.json and run: python scripts/build.py
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "assets" / "video"
POSTER_DIR = ROOT / "images" / "services"
MAX_WIDTH = 1920
MOBILE_WIDTH = 960


def find_ffmpeg() -> str:
    exe = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg  # type: ignore

            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            sys.exit("ffmpeg not found: install it, or set FFMPEG=path\\to\\ffmpeg.exe")
    return exe


def probe(ffmpeg: str, source: Path) -> tuple[float, int, float]:
    """(duration in seconds, width, frames per second) read from ffmpeg's own report."""
    info = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
    video = re.search(r"Video: .*?, (\d{3,5})x(\d{3,5}).*?, ([\d.]+) fps", info)
    return int(h) * 3600 + int(m) * 60 + float(s), int(video.group(1)), float(video.group(3))


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(result.stderr[-2000:])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Looping hero video for a service page")
    ap.add_argument("name", help="short name, e.g. vafi -> assets/video/service-vafi.mp4")
    ap.add_argument("source", type=Path)
    ap.add_argument("--start", type=float, default=0.0, help="seconds to skip at the start")
    ap.add_argument("--end", type=float, help="where to stop (seconds); default: the end")
    ap.add_argument("--loop", choices=("crossfade", "pingpong"), default="crossfade")
    ap.add_argument("--fade", type=float, default=1.0, help="crossfade length in seconds")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    duration, src_width, src_fps = probe(ffmpeg, args.source)
    start, end = args.start, min(args.end or duration, duration)
    length = end - start
    fps = src_fps / 2 if src_fps > 30 else src_fps  # 50 -> 25: smooth enough, half the size
    fps_text = f"{fps:.3f}".rstrip("0").rstrip(".")
    width = min(MAX_WIDTH, src_width)
    base = (f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale={width}:-2:flags=lanczos,fps={fps_text},split[a][b]")
    if args.loop == "crossfade":
        d = args.fade
        graph = (f"{base};[a]trim=start={d},setpts=PTS-STARTPTS[main];"
                 f"[b]trim=end={d},setpts=PTS-STARTPTS[head];"
                 f"[main][head]xfade=transition=fade:duration={d}:offset={length - 2 * d:.3f},format=yuv420p[v]")
    else:
        frames = int(round(length * fps))
        # backwards part without its first and last frame (they repeat the forward ends)
        graph = (f"{base};[b]reverse,trim=start_frame=1:end_frame={frames - 1},setpts=PTS-STARTPTS[r];"
                 f"[a][r]concat=n=2:v=1:a=0,format=yuv420p[v]")

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    desktop = VIDEO_DIR / f"service-{args.name}.mp4"
    mobile = VIDEO_DIR / f"service-{args.name}-mobile.mp4"
    x264 = ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-an"]
    run([ffmpeg, "-hide_banner", "-y", "-i", str(args.source), "-filter_complex", graph,
         "-map", "[v]", *x264, "-crf", "26", str(desktop)])
    run([ffmpeg, "-hide_banner", "-y", "-i", str(desktop), "-vf", f"scale={MOBILE_WIDTH}:-2:flags=lanczos",
         *x264, "-crf", "29", str(mobile)])

    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "first.png"
        run([ffmpeg, "-hide_banner", "-y", "-i", str(desktop), "-frames:v", "1", str(frame)])
        poster = POSTER_DIR / f"{args.name}-poster.webp"
        with Image.open(frame) as im:
            im = im.convert("RGB")
            if im.width > 1600:
                im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
            im.save(poster, "WEBP", quality=78, method=6)

    _, out_width, _ = probe(ffmpeg, desktop)
    out_seconds = probe(ffmpeg, desktop)[0]
    for f in (desktop, mobile, poster):
        print(f"{f.relative_to(ROOT).as_posix()}  {f.stat().st_size / 1_048_576:.1f} MB")
    print(f"{args.loop}, {out_seconds:.1f} s, {out_width} px wide, {fps_text} fps")


if __name__ == "__main__":
    main()
