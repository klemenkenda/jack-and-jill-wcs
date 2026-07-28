#!/usr/bin/env python
"""
split_book.py — turn one giant Google-Docs-exported Markdown file into
per-chapter Markdown files plus a folder of real image files.

Why this exists
----------------
Google Docs' "Download as Markdown" export embeds every image inline as a
base64 data: URI, e.g.:

    [image7]: <data:image/png;base64,iVBORw0KGgo....(huge)....>
    ...
    ![][image7]

That makes the .md file huge and unreadable/uneditable. This script:

  1. Finds every `[imageN]: <data:image/TYPE;base64,DATA>` reference
     definition, decodes it, and writes it to images/imageN.<ext>.
  2. Drops any heading with no real text — Google Docs uses empty `## `
     lines as a vertical-spacing hack on print layout pages (the title
     page has 7 of them), and each would otherwise become a blank
     entry in the EPUB's table of contents.
  3. Splits the (now much smaller) text into chapters — one per
     top-level `# ` heading, plus a forced break at any heading listed
     in FORCE_SPLIT_HEADINGS (e.g. "ZAHVALE", so the acknowledgements
     become their own chapter instead of trailing the last real
     chapter). The first two chapters (title page, inside/front matter)
     get fixed filenames via FILENAME_OVERRIDES rather than a slug
     derived from their heading text, and are left exactly as-is
     (no further splitting, no numbering — their `##` headings are
     print-layout spacers, not real sections).
  4. Every other chapter is further split into one file per `##`
     heading, written to chapters/PART-SUB-slug.md. Chapters that came
     from a genuine top-level `#` heading also get their headings
     numbered in the text itself — `#` becomes "N.", `##` becomes
     "N.M", `###` becomes "N.M.K." — so e.g. chapter 2's third `##`
     section's second `###` subsection reads "2.3.2.". Chapters
     produced by a FORCE_SPLIT_HEADINGS break (back matter, e.g.
     Zahvale) are still split on `##` but are NOT numbered, matching
     how front/back matter conventionally isn't part of a book's
     numbered chapter sequence.
  5. Re-inserts, into each resulting file, only the `[imageN]: images/...`
     definitions that its own `![][imageN]` usages need — Google
     Docs' export clusters ALL of them near the end of the document
     regardless of where each image is actually used, so without this
     step most files would have broken images.

The book's cover graphic isn't handled here — Google Docs' Markdown
export drops floating/anchored images, so the cover never makes it into
the base64 data at all. See upgrade_images.py, which pulls it (and
higher-resolution versions of the 22 inline images) from a reference
.epub export instead; it writes images/cover.jpg, and build_epub.py
wires that up as the EPUB's cover via metadata.yaml's cover-image field.

Re-run this any time the source .md changes (e.g. re-exported from
Google Docs) — it overwrites chapters/ and images/*.png from scratch.
Hand-written prose edits belong in the chapters/ files, not the source
.md, since this script will blow chapters/ away on the next run.

Usage (from the project root):
    python scripts/split_book.py [source.md]

If source.md is omitted, the script looks for the single .md file in
the project root (other than ones inside chapters/).
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent.parent  # project root (scripts/ is one level down)
IMAGES_DIR = ROOT / "images"
CHAPTERS_DIR = ROOT / "chapters"

IMAGE_DEF_RE = re.compile(
    r"^\[image(\d+)\]:\s*<data:image/(\w+);base64,([^>]+)>\s*$",
    re.MULTILINE,
)
HEADING_RE = re.compile(r"^(#{1,6}) .*$", re.MULTILINE)
BOLD_ITALIC_RE = re.compile(r"[*_]{1,3}")

# Sub-headings (any level) that should start a new chapter even though they
# aren't a top-level `# ` heading — e.g. acknowledgements shouldn't just
# trail on the end of the last content chapter.
FORCE_SPLIT_HEADINGS = {"ZAHVALE"}

# Fixed filenames (without the NN- prefix or .md) for the first N chapters,
# overriding the default slug-from-heading-text naming.
FILENAME_OVERRIDES = {0: "title", 1: "inside"}


def find_source_md() -> Path:
    candidates = [
        p for p in ROOT.glob("*.md")
        if p.is_file()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        sys.exit("No .md file found next to split_book.py. Pass the path explicitly.")
    sys.exit(
        "Multiple .md files found in the project root; pass the source file "
        "explicitly: python split_book.py \"Your Book.md\"\n"
        + "\n".join(f"  - {p.name}" for p in candidates)
    )


def extract_images(content: str) -> tuple[str, dict[str, str]]:
    """Decode every base64 image reference to a file.

    Google Docs' Markdown export clusters ALL reference-link definitions
    (`[imageN]: <data:...>`) together near the end of the document,
    regardless of where each image is actually used in the text. If we
    left the rewritten `[imageN]: images/imageN.ext` definitions in
    place, they'd all land in whichever chapter happens to contain that
    tail section — leaving every other chapter with `![][imageN]`
    usages but no matching definition, i.e. broken images the moment
    that chapter is viewed/built on its own.

    So instead: strip the definition lines out of the flowing text
    entirely, and hand back an {id: relative_path} map. write_chapters()
    re-inserts, into each chapter, only the definitions that chapter's
    own `![][imageN]` usages need.
    """
    IMAGES_DIR.mkdir(exist_ok=True)
    # Clear out any previously extracted/upgraded imageN.* (any extension) so a
    # re-run never leaves stale files (e.g. an image1.jpg from a prior
    # upgrade_images.py run) alongside the freshly extracted image1.png.
    # cover.jpg is untouched — it isn't produced by this function.
    for old in IMAGES_DIR.glob("image*.*"):
        if re.match(r"image\d+\.\w+$", old.name):
            old.unlink()
    image_paths: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        idx, ext, b64_data = match.group(1), match.group(2), match.group(3)
        raw = base64.b64decode(re.sub(r"\s+", "", b64_data))
        filename = f"image{idx}.{ext}"
        (IMAGES_DIR / filename).write_bytes(raw)
        image_paths[idx] = f"images/{filename}"
        return ""

    new_content = IMAGE_DEF_RE.sub(replace, content)
    print(f"Extracted {len(image_paths)} images to {IMAGES_DIR.relative_to(ROOT)}/")
    return new_content, image_paths


def clean_heading_text(heading_line: str) -> str:
    text = heading_line.lstrip("#").strip()
    text = BOLD_ITALIC_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_blank_headings(content: str) -> str:
    """Drop headings with no real text (any level).

    Google Docs uses empty `## ` lines as a vertical-spacing hack on print
    layout pages (the title page has 7 of them). They carry no content, but
    each one still becomes its own (empty) entry in the EPUB's table of
    contents, so they need to go entirely rather than just being skipped as
    split/numbering points.
    """

    def repl(m: re.Match) -> str:
        return "" if not clean_heading_text(m.group()) else m.group()

    return HEADING_RE.sub(repl, content)


def slugify(text: str, max_words: int = 6) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-zA-Z0-9]+", ascii_text.lower())
    slug = "-".join(words[:max_words])
    return slug or "chapter"


def split_chapters(content: str) -> list[tuple[str, str, bool]]:
    """Return list of (title, body_markdown, is_real_chapter), split on
    top-level `# ` headings and on any heading matching FORCE_SPLIT_HEADINGS
    regardless of level. is_real_chapter is False for a FORCE_SPLIT_HEADINGS
    break (back matter, e.g. Zahvale) — used later to decide what gets
    chapter numbering."""
    split_points = []  # (offset, level, title)
    for m in HEADING_RE.finditer(content):
        level = len(m.group(1))
        title = clean_heading_text(m.group())
        if level == 1 or title.upper() in FORCE_SPLIT_HEADINGS:
            split_points.append((m.start(), level, title))
    if not split_points:
        sys.exit("No top-level '# ' headings found — nothing to split on.")

    chapters = []
    for i, (start, level, title) in enumerate(split_points):
        end = split_points[i + 1][0] if i + 1 < len(split_points) else len(content)
        body = content[start:end].rstrip() + "\n"
        if level != 1:
            # Forced sub-heading split (e.g. "## ZAHVALE") becomes its own
            # chapter, so promote its leading heading to top-level for a
            # consistent chapter structure and correct EPUB TOC nesting.
            body = re.sub(r"^#{1,6} ", "# ", body, count=1)
        chapters.append((title, body, level == 1))
    return chapters


def split_into_subchapters(body: str, chapter_number: int | None) -> list[tuple[str, str]]:
    """Split one chapter's body into (title, sub_body) pieces, one per
    non-blank `##` heading (the leading piece, up to the first `##`, keeps
    the chapter's own title). If chapter_number is given, also numbers the
    `#`/`##`/`###` headings in place ("#" -> "N.", "##" -> "N.M",
    "###" -> "N.M.K."). Blank headings and H4+ are left untouched and never
    split on."""
    h2 = h3 = 0
    pieces: list[tuple[str, str]] = []
    current_title = ""
    buf: list[str] = []
    pos = 0

    for m in HEADING_RE.finditer(body):
        level = len(m.group(1))
        text = clean_heading_text(m.group())
        buf.append(body[pos:m.start()])
        pos = m.end()
        line = m.group()

        if level == 2 and text:
            pieces.append((current_title, "".join(buf)))
            buf = []
            current_title = text
            h2 += 1
            h3 = 0
            if chapter_number is not None:
                line = re.sub(r"^## ", f"## {chapter_number}.{h2} ", line, count=1)
        elif level == 1 and text:
            current_title = text
            if chapter_number is not None:
                line = re.sub(r"^# ", f"# {chapter_number}. ", line, count=1)
        elif level == 3 and text and chapter_number is not None:
            h3 += 1
            line = re.sub(r"^### ", f"### {chapter_number}.{h2}.{h3}. ", line, count=1)
        buf.append(line)

    buf.append(body[pos:])
    pieces.append((current_title, "".join(buf)))
    return pieces


USAGE_RE = re.compile(r"!\[[^\]]*\]\[image(\d+)\]")


def append_image_definitions(body: str, image_paths: dict[str, str]) -> str:
    """Append only the [imageN]: path definitions this chapter's usages need."""
    used_ids = sorted(set(USAGE_RE.findall(body)), key=int)
    if not used_ids:
        return body
    def_lines = [f"[image{idx}]: {image_paths[idx]}" for idx in used_ids if idx in image_paths]
    return body.rstrip("\n") + "\n\n" + "\n".join(def_lines) + "\n"


def write_chapters(chapters: list[tuple[str, str, bool]], image_paths: dict[str, str]) -> None:
    if CHAPTERS_DIR.exists():
        for old_file in CHAPTERS_DIR.glob("*.md"):
            old_file.unlink()
    CHAPTERS_DIR.mkdir(exist_ok=True)

    # Filenames are PART-SUB-slug.md: front-matter chapters (FILENAME_OVERRIDES)
    # all share part 00, numbered by sub-index (00-0-title.md, 00-1-inside.md, ...);
    # every other chapter gets its own part number, and is itself split into
    # one file per `##` section, numbered as sub-index 0, 1, 2, ...
    # (01-0-slug.md, 01-1-slug.md, ...). Real chapters (is_real_chapter=True)
    # also get "N."/"N.M"/"N.M.K." numbering baked into their heading text;
    # back-matter chapters (e.g. Zahvale, from FORCE_SPLIT_HEADINGS) are
    # still split on `##` but left unnumbered.
    front_matter_order = sorted(FILENAME_OVERRIDES)
    part_counter = 1
    for i, (title, body, is_real_chapter) in enumerate(chapters):
        body = re.sub(r"\n{3,}", "\n\n", body)  # tidy up gaps left by removed image defs

        if i in FILENAME_OVERRIDES:
            part = 0
            slug = FILENAME_OVERRIDES[i]
            sub_pieces = [(title, body)]
            sub_offset = front_matter_order.index(i)
        else:
            part = part_counter
            part_counter += 1
            chapter_number = part if is_real_chapter else None
            sub_pieces = split_into_subchapters(body, chapter_number)
            sub_offset = 0

        used_slugs: dict[str, int] = {}  # deduped within this chapter's own sub-pieces only
        for sub, (sub_title, sub_body) in enumerate(sub_pieces, start=sub_offset):
            sub_body = append_image_definitions(sub_body, image_paths)
            if i in FILENAME_OVERRIDES:
                slug_for_file = slug
            else:
                slug_for_file = slugify(sub_title)
                used_slugs[slug_for_file] = used_slugs.get(slug_for_file, 0) + 1
                if used_slugs[slug_for_file] > 1:
                    slug_for_file = f"{slug_for_file}-{used_slugs[slug_for_file]}"
            filename = f"{part:02d}-{sub}-{slug_for_file}.md"
            (CHAPTERS_DIR / filename).write_text(sub_body, encoding="utf-8")
            print(f"  {filename}  ({sub_title!r})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="Path to the source .md file")
    args = parser.parse_args()

    source_path = Path(args.source) if args.source else find_source_md()
    print(f"Reading {source_path.name} ...")
    content = source_path.read_text(encoding="utf-8")

    content, image_paths = extract_images(content)
    content = strip_blank_headings(content)
    chapters = split_chapters(content)

    print(f"Splitting into {len(chapters)} chapters:")
    write_chapters(chapters, image_paths)

    print("\nDone. Edit files under chapters/ freely, then run build_epub.py.")


if __name__ == "__main__":
    main()
