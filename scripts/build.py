#!/usr/bin/env python
"""
build.py — assemble chapters/*.md into an .epub (via Pandoc) and a
matching .pdf (via Pandoc's typst writer + the typst compiler), from the
same numbered/versioned chapter text.

Re-run this any time you edit a file under chapters/ (fix a table, reword
a paragraph, add a heading, whatever) — it just re-runs over whatever is
currently in chapters/, so there's nothing to regenerate by hand.

Requires:
  - Pandoc (https://pandoc.org) on PATH.
  - `pip install typst pyyaml` (only needed for the PDF; the EPUB alone
    only needs Pandoc).

Usage (from the project root):
    python scripts/build.py [--no-epub] [--no-pdf] [-o OUTPUT.epub] [--pdf-output OUTPUT.pdf]

Why a PDF needs more than Pandoc's stock markdown->typst conversion
--------------------------------------------------------------------
The chapter source was written for the EPUB: tables and figures are raw
HTML (`<table>`, `<figure>`) so they carry EPUB-accessibility markup
(`scope`, `<figcaption>`), and callouts/glossary/criteria coloring are
pandoc fenced-divs/bracketed-spans with CSS classes (`::: box`,
`[Timing]{.crit-timing}`) that only epub-style.css knows how to render.
Pandoc's typst writer doesn't read epub-style.css and has no idea what a
"box" or "crit-timing" class means, so left alone it silently drops
class info or flattens raw HTML into plain paragraphs. scripts/pdf-filter.lua
fixes both problems (see its own docstring), and pdf-template.typ defines
the functions (#book_box, #crit_timing, ...) the filter's output calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # project root (scripts/ is one level down)
CHAPTERS_DIR = ROOT / "chapters"
METADATA_FILE = ROOT / "metadata.yaml"
CSS_FILE = ROOT / "epub-style.css"
PDF_TEMPLATE_FILE = ROOT / "pdf-template.typ"
PDF_FILTER_FILE = Path(__file__).resolve().parent / "pdf-filter.lua"
FONTS_DIR = ROOT / "fonts"
IMAGES_DIR = ROOT / "images"
DIST_DIR = ROOT / "dist"
VERSION_FILE = ROOT / "version.json"
DEFAULT_EPUB_OUTPUT = DIST_DIR / "Jack and Jill tekmovanja v WCS.epub"
DEFAULT_PDF_OUTPUT = DIST_DIR / "Jack and Jill tekmovanja v WCS.pdf"

# Chapter files with this prefix are the EPUB's title/colophon pages —
# for the PDF they're replaced entirely by a hand-built title page (see
# build_title_page_typst), since a fixed page can do a real cover-image
# layout a reflowable EPUB chapter can't.
PDF_FRONT_MATTER_PREFIX = "00-"

# A chapter file starting with this line (as its very first line) is front/back
# matter (title page, acknowledgements, ...) and is excluded from the
# chapter/section/subsection auto-numbering below.
UNNUMBERED_MARKER = "<!-- unnumbered -->"

HEADING_RE = re.compile(r'^(#{1,6})(\s+)(.*)$')


def strip_heading_emphasis(text: str) -> str:
    """Drop manual bold/italic markup from a heading's text.

    Headings are bold automatically via epub-style.css, so any manual
    ``**bold**`` in a heading is redundant; ``***bold italic***`` collapses to
    plain ``*italic*`` since the surrounding bold is already implied.
    """
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'*\1*', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    return text


def number_and_clean_chapter(text: str, counters: dict[str, int]) -> str:
    """Strip manual heading bold everywhere, and auto-number h1/h2/h3 headings.

    Numbering (chapter / chapter.section / chapter.section.subsection) is
    tracked in `counters` across the whole book. Files whose first line is
    UNNUMBERED_MARKER are front/back matter: that marker line is dropped and
    their headings are left unnumbered without disturbing the running count.
    """
    lines = text.splitlines()
    numbered = True
    if lines and lines[0].strip() == UNNUMBERED_MARKER:
        numbered = False
        lines = lines[1:]
        if lines and lines[0].strip() == "":
            lines = lines[1:]

    out_lines = []
    for line in lines:
        m = HEADING_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        hashes, gap, rest = m.groups()
        level = len(hashes)
        rest = strip_heading_emphasis(rest)

        prefix = ""
        if numbered and level == 1:
            counters["chapter"] += 1
            counters["section"] = 0
            counters["subsection"] = 0
            prefix = f"{counters['chapter']}. "
        elif numbered and level == 2:
            counters["section"] += 1
            counters["subsection"] = 0
            prefix = f"{counters['chapter']}.{counters['section']} "
        elif numbered and level == 3:
            counters["subsection"] += 1
            prefix = f"{counters['chapter']}.{counters['section']}.{counters['subsection']}. "

        out_lines.append(f"{hashes}{gap}{prefix}{rest}")
    return "\n".join(out_lines) + "\n"


def is_numbered_chapter(text: str) -> bool:
    """True if `text` is a "real" chapter: not front/back matter, and its
    first heading is level 1 (this is what get numbered/counted as a chapter
    by `number_and_clean_chapter`).
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == UNNUMBERED_MARKER:
        return False
    for line in lines:
        if line.strip() == "":
            continue
        m = HEADING_RE.match(line)
        return bool(m and len(m.group(1)) == 1)
    return False


def numbered_section_headings(text: str) -> list[str]:
    """Return the raw text of every level-2 ("## ") heading in `text`.

    A "## " heading is a new named section (e.g. "TEČAJI", "PRIVATNE URE")
    within a chapter file, the same unit `number_and_clean_chapter` numbers
    as chapter.section. Front/back matter (UNNUMBERED_MARKER) has no such
    headings that should count.
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == UNNUMBERED_MARKER:
        return []
    headings = []
    for line in lines:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 2:
            headings.append(strip_heading_emphasis(m.group(3)).strip())
    return headings


PIPE_DELIM_RE = re.compile(r'^\|\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')


def lint_pipe_tables(texts: dict[Path, str]) -> list[str]:
    """Flag pipe-table blocks that would render badly or broken in the epub.

    A `<table>` is an atomic box that most e-readers can't split across a
    page, so a single-cell table wrapping a whole paragraph (the leftover
    shape from this book's Google Docs export) either gets clipped or pushed
    onto a blank page, and its content ends up mis-styled as `<th>` besides.
    Real, short, genuinely tabular content should use ``| col | col |``
    tables; long free-flowing text should be a ``::: box`` div instead.
    This also catches a table row that's missing its leading ``|`` (so it
    silently drops out of the table instead of erroring).
    """
    problems = []
    for f, text in texts.items():
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            if lines[i].startswith("|"):
                j = i
                while j < len(lines) and lines[j].startswith("|"):
                    j += 1
                block = lines[i:j]
                delim_idx = next((k for k, l in enumerate(block) if PIPE_DELIM_RE.match(l)), None)
                if delim_idx is None:
                    problems.append(
                        f"{f.name}:{i + 1}: pipe-table block has no delimiter row "
                        f"(likely a row missing its leading '|')"
                    )
                elif delim_idx == 0 and len(block) == 2:
                    cols = block[1].count("|") - 1
                    if cols <= 1:
                        problems.append(
                            f"{f.name}:{i + 1}: single-cell pipe 'table' — this is the "
                            f"Google-Docs export artifact that renders as an unsplittable "
                            f"<table><th> block; wrap the text in '::: box' / ':::' instead"
                        )
                i = j
            else:
                i += 1
    return problems


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"major": 0, "minor": 0, "patch": 0, "chapters": []}


def bump_version(
    version: dict,
    current_chapters: list[str],
    current_sections: list[str],
    bump_major: bool,
) -> tuple[dict, str, str]:
    """Apply the versioning rules and return (new_version, "MAJOR.MINOR.PATCH", note).

    MAJOR only moves via --bump-major (manual). Otherwise: if any chapter
    file or "## " section heading wasn't present in the last recorded
    build, MINOR goes up by the number of new chapters/sections and PATCH
    resets to 0 — adding a whole new named section is as reader-visible as
    adding a whole new chapter. Failing that, every build just bumps PATCH.
    """
    known_chapters = set(version.get("chapters", []))
    known_sections = set(version.get("sections", []))
    new_chapters = [c for c in current_chapters if c not in known_chapters]
    new_sections = [s for s in current_sections if s not in known_sections]

    if bump_major:
        version["major"] += 1
        version["minor"] = 0
        version["patch"] = 0
        note = "major bump (manual)"
    elif new_chapters or new_sections:
        version["minor"] += len(new_chapters) + len(new_sections)
        version["patch"] = 0
        parts = []
        if new_chapters:
            plural = "s" if len(new_chapters) != 1 else ""
            parts.append(f"+{len(new_chapters)} new chapter{plural}: {', '.join(new_chapters)}")
        if new_sections:
            plural = "s" if len(new_sections) != 1 else ""
            parts.append(f"+{len(new_sections)} new section{plural}: {', '.join(new_sections)}")
        note = "minor bump (" + "; ".join(parts) + ")"
    else:
        version["patch"] += 1
        note = "patch bump (compile)"

    version["chapters"] = current_chapters
    version["sections"] = current_sections
    version_str = f"{version['major']}.{version['minor']}.{version['patch']}"
    return version, version_str, note


def build_epub(processed_files: list[Path], output: Path) -> None:
    pandoc = shutil.which("pandoc")
    cmd = [
        pandoc,
        "--metadata-file", str(METADATA_FILE),
        *[str(f) for f in processed_files],
        "-o", str(output),
        "-f", "markdown+smart+pipe_tables",
        "-t", "epub3",
        "--toc",
        "--toc-depth", "3",
        "--split-level", "1",
        "--resource-path", os.pathsep.join([str(CHAPTERS_DIR), str(ROOT)]),
    ]
    if CSS_FILE.exists():
        cmd += ["--css", str(CSS_FILE)]
    if FONTS_DIR.exists():
        for font_file in sorted(FONTS_DIR.glob("*.ttf")):
            cmd += ["--epub-embed-font", str(font_file)]

    print("\nRunning pandoc (epub) ...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"pandoc failed with exit code {result.returncode}")

    size_mb = output.stat().st_size / 1_000_000
    print(f"Built {output.relative_to(ROOT)} ({size_mb:.1f} MB)")

    epubcheck = shutil.which("epubcheck")
    if epubcheck:
        print("\nRunning epubcheck ...")
        subprocess.run([epubcheck, str(output)], cwd=ROOT)
    else:
        print("(epubcheck not found on PATH - skipping structural validation.)")


def load_metadata() -> dict:
    import yaml
    return yaml.safe_load(METADATA_FILE.read_text(encoding="utf-8"))


def typst_str(s: str) -> str:
    """Quote `s` as a typst string literal, for passing metadata text as a
    function-call argument (title_page(...), impressum_page(...))."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def typst_str_array(items: list[str]) -> str:
    return "(" + ", ".join(typst_str(i) for i in items) + ",)"


def build_title_page_typst(metadata: dict, version_str: str) -> str:
    cover = metadata.get("cover-image")
    if not cover or not (ROOT / cover).exists():
        sys.exit(f"metadata.yaml's cover-image ({cover!r}) is missing — the PDF title page needs it.")
    # Chapter .typ files live one level below the project root (in a
    # "chapters" dir mirroring the real layout), so cover-image's
    # ROOT-relative path needs a "../" to reach it from there — same
    # convention the chapter markdown already uses for figures.
    cover_path = f"../{cover}"

    title_lines = metadata.get("title-lines") or [metadata.get("title", "")]

    title_page_call = "#title_page({}, {}, {}, {}, {}, {})".format(
        typst_str_array(title_lines),
        typst_str(metadata.get("subtitle", "")),
        typst_str(metadata.get("author", "")),
        typst_str(metadata.get("publisher", "")),
        typst_str(version_str),
        typst_str(cover_path),
    )
    impressum_call = "#impressum_page({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
        typst_str(metadata.get("title", "")),
        typst_str(metadata.get("subtitle", "")),
        typst_str(metadata.get("author", "")),
        typst_str(metadata.get("publisher", "")),
        typst_str(metadata.get("place", "")),
        typst_str(str(metadata.get("year", ""))),
        typst_str(metadata.get("rights", "")),
        typst_str(metadata.get("license", "")),
        typst_str(metadata.get("cover-credit", "")),
        typst_str(version_str),
        typst_str(metadata.get("isbn", "") or ""),
    )

    return f"""
{title_page_call}
{impressum_call}
#outline(depth: 3, title: [Kazalo vsebine])
#pagebreak(weak: true)
"""


def run_pandoc_to_typst(files: list[Path]) -> str:
    pandoc = shutil.which("pandoc")
    cmd = [
        pandoc,
        # markdown_in_html_blocks (on by default) hands the reader one
        # RawBlock per HTML *tag* with the cell/caption text parsed as
        # markdown paragraphs in between it; disabling it hands us one
        # RawBlock per whole <table>/<figure> element instead, which is
        # what scripts/pdf-filter.lua needs to re-parse them successfully.
        "-f", "markdown-markdown_in_html_blocks+smart+pipe_tables",
        "-t", "typst",
        "--lua-filter", str(PDF_FILTER_FILE),
        *[str(f) for f in files],
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        sys.exit(f"pandoc (typst) failed with exit code {result.returncode}:\n{result.stderr}")
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)
    return result.stdout


def build_pdf(processed_files: list[Path], version_str: str, output: Path) -> None:
    try:
        import typst
    except ImportError:
        sys.exit(
            "The `typst` package is required to build the PDF "
            "(pip install typst pyyaml), or pass --no-pdf to skip it."
        )

    body_files = [f for f in processed_files if not f.name.startswith(PDF_FRONT_MATTER_PREFIX)]
    body_typst = run_pandoc_to_typst(body_files)

    metadata = load_metadata()
    title_page = build_title_page_typst(metadata, version_str)

    full_typst = (
        PDF_TEMPLATE_FILE.read_text(encoding="utf-8")
        + "\n"
        + title_page
        + "\n"
        + body_typst
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build_pdf_") as tmp_dir:
        tmp_dir = Path(tmp_dir)
        chapters_dir = tmp_dir / "chapters"
        chapters_dir.mkdir()
        (chapters_dir / "book.typ").write_text(full_typst, encoding="utf-8")
        if IMAGES_DIR.exists():
            shutil.copytree(IMAGES_DIR, tmp_dir / "images")

        print("\nCompiling PDF (typst) ...")
        try:
            typst.compile(
                str(chapters_dir / "book.typ"),
                output=str(output),
                root=str(tmp_dir),
                font_paths=[str(FONTS_DIR)],
            )
        except Exception as e:
            sys.exit(f"typst compile failed:\n{e}")

    size_mb = output.stat().st_size / 1_000_000
    print(f"Built {output.relative_to(ROOT)} ({size_mb:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output", type=Path, default=DEFAULT_EPUB_OUTPUT,
        help=f"Output .epub path (default: {DEFAULT_EPUB_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--pdf-output", type=Path, default=DEFAULT_PDF_OUTPUT,
        help=f"Output .pdf path (default: {DEFAULT_PDF_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument("--no-epub", action="store_true", help="Skip building the .epub.")
    parser.add_argument("--no-pdf", action="store_true", help="Skip building the .pdf.")
    parser.add_argument(
        "--bump-major", action="store_true",
        help="Manually bump the MAJOR version (resets MINOR and PATCH to 0).",
    )
    parser.add_argument(
        "--preview-html", type=Path, default=None,
        help="Also render a single standalone HTML file at this path (same CSS/content) "
             "for a quick check in a regular browser, light and dark.",
    )
    parser.add_argument(
        "--no-lint", action="store_true",
        help="Skip the pipe-table lint (see lint_pipe_tables). Not recommended.",
    )
    args = parser.parse_args()

    pandoc = shutil.which("pandoc")
    if not pandoc:
        sys.exit(
            "Pandoc not found on PATH. Install it from https://pandoc.org/installing.html "
            "and try again."
        )

    chapter_files = sorted(CHAPTERS_DIR.glob("*.md"))
    if not chapter_files:
        sys.exit(f"No chapter files found in {CHAPTERS_DIR.relative_to(ROOT)}/.")

    if not METADATA_FILE.exists():
        sys.exit(f"Missing {METADATA_FILE.relative_to(ROOT)} — book title/author metadata.")

    print("Chapters (in order):")
    for f in chapter_files:
        print(f"  {f.relative_to(ROOT)}")

    texts = {f: f.read_text(encoding="utf-8") for f in chapter_files}

    if not args.no_lint:
        problems = lint_pipe_tables(texts)
        if problems:
            print("\nPipe-table lint failed:")
            for p in problems:
                print(f"  {p}")
            sys.exit(
                "\nFix the chapter source (or pass --no-lint to skip this check, not recommended)."
            )

    current_chapters = [f.name for f in chapter_files if is_numbered_chapter(texts[f])]
    current_sections = [
        heading
        for f in chapter_files
        for heading in numbered_section_headings(texts[f])
    ]
    version = load_version()
    version, version_str, version_note = bump_version(
        version, current_chapters, current_sections, args.bump_major
    )
    print(f"\nVersion: {version_str} ({version_note})")

    counters = {"chapter": 0, "section": 0, "subsection": 0}
    with tempfile.TemporaryDirectory(prefix="build_") as tmp_dir:
        tmp_dir = Path(tmp_dir)
        processed_files = []
        for f in chapter_files:
            processed = number_and_clean_chapter(texts[f], counters)
            processed = processed.replace("{{VERSION}}", version_str)
            tmp_file = tmp_dir / f.name
            tmp_file.write_text(processed, encoding="utf-8")
            processed_files.append(tmp_file)

        if not args.no_epub:
            build_epub(processed_files, args.output)

        if not args.no_pdf:
            build_pdf(processed_files, version_str, args.pdf_output)

        if args.preview_html:
            args.preview_html.parent.mkdir(parents=True, exist_ok=True)
            html_cmd = [
                pandoc,
                "--metadata-file", str(METADATA_FILE),
                *[str(f) for f in processed_files],
                "-o", str(args.preview_html),
                "-f", "markdown+smart+pipe_tables",
                "-t", "html5",
                "--standalone",
                "--toc",
                "--toc-depth", "3",
                "--resource-path", os.pathsep.join([str(CHAPTERS_DIR), str(ROOT)]),
                "--embed-resources",
            ]
            if CSS_FILE.exists():
                # The epub-only @font-face rules point at "../fonts/...", a
                # path that's valid inside the built .epub's internal layout
                # but not relative to this standalone HTML file; drop them so
                # --embed-resources doesn't choke trying to resolve them.
                # The preview is for checking table/box/blockquote layout and
                # light/dark theming, not font fidelity.
                preview_css = re.sub(
                    r'@font-face\s*\{[^}]*\}', '', CSS_FILE.read_text(encoding="utf-8")
                )
                preview_css_file = tmp_dir / "preview.css"
                preview_css_file.write_text(preview_css, encoding="utf-8")
                html_cmd += ["--css", str(preview_css_file)]
            print("\nRendering HTML preview ...")
            html_result = subprocess.run(html_cmd, cwd=ROOT)
            if html_result.returncode != 0:
                sys.exit(f"pandoc HTML preview failed with exit code {html_result.returncode}")
            print(f"Preview: {args.preview_html.relative_to(ROOT) if args.preview_html.is_relative_to(ROOT) else args.preview_html}")

    VERSION_FILE.write_text(json.dumps(version, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
