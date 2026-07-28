#!/usr/bin/env python
"""
upgrade_images.py — replace the low-res images extracted from the .md
with higher-resolution versions pulled from a reference .epub.

Why this is needed
-------------------
Google Docs' two export paths compress images very differently:
  - "Download as Markdown" embeds images at ~569px wide (fine for a
    printed page column, soft on a retina e-reader screen).
  - "Download as EPUB" keeps them near-original resolution (up to
    ~2000px wide) — but also 10-100x the file size, uncompressed.

Both exports number their images independently (image7 in the .md is
NOT image7 in the .epub) and use a different image count, because the
Markdown exporter silently drops floating/anchored images (that's
where the book's cover graphic went — see split_book.py's cover
handling). This script re-derives the correspondence itself, every
time, by matching:
  1. reading order — both exports walk the document top-to-bottom;
     once you set aside any leading images that only exist in the
     epub (cover-type images with no Markdown counterpart), the
     remaining images line up 1:1 in the same order.
  2. aspect ratio — a same-image sanity check across a resize/recompress
     that can only change resolution, not proportions.

Given a match, each epub image is downscaled to MAX_WIDTH and
recompressed, then written over the corresponding images/imageN.*
file that split_book.py produced — no chapter .md file needs to
change, since they already reference images/imageN.* by filename.

Usage (from the project root):
    python scripts/upgrade_images.py ["Reference.epub"]

If no path is given, it looks for the single .epub file in the
project root. Run this AFTER split_book.py (it needs images/imageN.*
already extracted, to know how many images to match against and to
compare aspect ratios).
"""
from __future__ import annotations

import re
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent  # project root (scripts/ is one level down)
IMAGES_DIR = ROOT / "images"
MAX_WIDTH = 1400          # px — generous for e-reader retina screens
PNG_SIZE_LIMIT = 600_000  # bytes — above this, fall back to JPEG
JPEG_QUALITY = 88
RATIO_TOLERANCE = 0.08    # sanity-check window on aspect ratio match

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def find_reference_epub() -> Path:
    candidates = list(ROOT.glob("*.epub"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        sys.exit("No reference .epub found in the project root. Pass its path explicitly.")
    sys.exit(
        "Multiple .epub files found; pass the reference file explicitly:\n"
        + "\n".join(f"  - {p.name}" for p in candidates)
    )


def png_dims(data: bytes) -> tuple[int, int]:
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    return w, h


def load_current_images() -> list[tuple[str, int, int]]:
    """Return [(filename, w, h), ...] for images/imageN.* in numeric order."""
    entries = []
    for p in IMAGES_DIR.glob("image*.*"):
        m = re.match(r"image(\d+)\.\w+$", p.name)
        if not m:
            continue
        with Image.open(p) as img:
            w, h = img.size
        entries.append((int(m.group(1)), p.name, w, h))
    entries.sort(key=lambda e: e[0])
    return [(name, w, h) for _, name, w, h in entries]


def load_epub_images(epub_path: Path) -> list[tuple[str, bytes, int, int]]:
    """Return [(filename, bytes, w, h), ...] in document reading order."""
    with zipfile.ZipFile(epub_path) as zf:
        xhtml_names = [n for n in zf.namelist() if n.endswith(".xhtml")]
        if not xhtml_names:
            sys.exit("No .xhtml content found inside the epub — unexpected epub structure.")
        # Assume a single main content document (true for Google Docs epub exports).
        xhtml_name = max(xhtml_names, key=lambda n: len(zf.read(n)))
        xhtml = zf.read(xhtml_name).decode("utf-8")
        base_dir = Path(xhtml_name).parent

        order = re.findall(r'<img[^>]*src="([^"]+)"', xhtml)
        images = []
        for src in order:
            img_path = str((base_dir / src).as_posix())
            if img_path not in zf.namelist():
                # try resolving relative to zip root as a fallback
                alt = src.lstrip("./")
                if alt in zf.namelist():
                    img_path = alt
                else:
                    print(f"  (skipping {src!r} — not found in epub archive)")
                    continue
            data = zf.read(img_path)
            w, h = png_dims(data)
            images.append((Path(img_path).name, data, w, h))
        return images


def match_and_upgrade(current: list[tuple[str, int, int]], epub_images: list[tuple[str, bytes, int, int]]) -> None:
    n_current = len(current)
    n_epub = len(epub_images)
    surplus = n_epub - n_current

    cover_candidate = None
    body_epub_images = epub_images
    if surplus == 1:
        cover_candidate = epub_images[0]
        body_epub_images = epub_images[1:]
        print(f"Treating leading epub image {cover_candidate[0]!r} as the cover.")
    elif surplus != 0:
        print(
            f"WARNING: epub has {n_epub} images, current set has {n_current} "
            f"(surplus {surplus}) — expected exactly 1 extra (the cover). "
            "Skipping automatic cover detection; body images below may misalign."
        )

    if len(body_epub_images) != n_current:
        sys.exit(
            f"Can't align {len(body_epub_images)} epub body images with "
            f"{n_current} current images — counts must match after removing the cover. "
            "Re-check the reference epub, or upgrade images manually."
        )

    print(f"\nMatching {n_current} images by reading order + aspect ratio:")
    for (cur_name, cw, ch), (epub_name, data, ew, eh) in zip(current, body_epub_images):
        cur_ratio = cw / ch
        epub_ratio = ew / eh
        diff = abs(cur_ratio - epub_ratio) / cur_ratio
        flag = "" if diff <= RATIO_TOLERANCE else "  <-- ratio mismatch, check manually!"
        print(f"  {cur_name:14s} ({cw}x{ch}, r={cur_ratio:.3f})  <-  "
              f"{epub_name:14s} ({ew}x{eh}, r={epub_ratio:.3f}){flag}")
        if diff > RATIO_TOLERANCE:
            continue
        save_upgraded(IMAGES_DIR / cur_name, data)

    if cover_candidate:
        cover_name, cover_data, cw, ch = cover_candidate
        save_upgraded(IMAGES_DIR / "cover.jpg", cover_data, force_jpeg=True)
        print(f"\nCover updated from {cover_name} ({cw}x{ch}).")


def save_upgraded(dest_path: Path, raw_png_bytes: bytes, force_jpeg: bool = False) -> None:
    import io
    img = Image.open(io.BytesIO(raw_png_bytes))
    if img.width > MAX_WIDTH:
        new_h = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)

    if force_jpeg:
        img.convert("RGB").save(dest_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return

    # Try PNG first (keeps sharp text/lines legible); fall back to JPEG if too big.
    png_bytes = io.BytesIO()
    img.save(png_bytes, "PNG", optimize=True)
    if png_bytes.tell() <= PNG_SIZE_LIMIT:
        dest_path.write_bytes(png_bytes.getvalue())
    else:
        jpeg_path = dest_path.with_suffix(".jpg")
        img.convert("RGB").save(jpeg_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        if jpeg_path != dest_path and dest_path.exists():
            dest_path.unlink()
        # If the filename changed (.png -> .jpg), the chapter .md must be updated too.
        if jpeg_path.name != dest_path.name:
            fix_chapter_references(dest_path.name, jpeg_path.name)


def fix_chapter_references(old_name: str, new_name: str) -> None:
    chapters_dir = ROOT / "chapters"
    for f in chapters_dir.glob("*.md"):
        text = f.read_text(encoding="utf-8")
        if old_name in text:
            f.write_text(text.replace(old_name, new_name), encoding="utf-8")
            print(f"  updated reference {old_name} -> {new_name} in {f.name}")


def main() -> None:
    epub_arg = sys.argv[1] if len(sys.argv) > 1 else None
    epub_path = Path(epub_arg) if epub_arg else find_reference_epub()
    print(f"Reference epub: {epub_path.name}")

    if not IMAGES_DIR.exists() or not any(IMAGES_DIR.glob("image*.*")):
        sys.exit("No images/imageN.* files found — run split_book.py first.")

    current = load_current_images()
    epub_images = load_epub_images(epub_path)
    print(f"Current images: {len(current)}   Epub images: {len(epub_images)}")

    match_and_upgrade(current, epub_images)

    total = sum(p.stat().st_size for p in IMAGES_DIR.glob("*"))
    print(f"\nDone. images/ is now {total / 1_000_000:.1f} MB.")
    print("Run build.py to rebuild the .epub/.pdf with the upgraded images.")


if __name__ == "__main__":
    main()
