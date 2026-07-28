# FORMATTING.md — EPUB authoring rules

Rules for producing a structurally rich EPUB (tables, figures, lists, code) that renders
uniformly across Kindle, Apple Books, Kobo, Google Play Books and Readium-based readers.

**Guiding principle:** the Kindle converter is the lowest common denominator. Nothing that
matters may depend on the reading system honouring our CSS. If the stylesheet were deleted
entirely, the book must still be readable and correctly ordered.

---

## 1. Target and toolchain

- Author **EPUB 3 (XHTML5)** as the single master format. Never hand-author MOBI/AZW3 —
  upload the EPUB to KDP / Send-to-Kindle and let Amazon convert.
- Single source of truth in version control (AsciiDoc via Asciidoctor, or Markdown via
  Pandoc). Builds must be reproducible; do not hand-edit generated output in Sigil.
- The base stylesheet is a **fixed contract**. Changes to it are reviewed like code.
- `python scripts/build.py` builds a companion print **PDF** alongside the EPUB from the
  same chapter source (via Pandoc's typst writer + the `typst` PyPI package — see that
  script's and `pdf-template.typ`'s docstrings). It's a fixed-page rendering of the same
  content, not a second format to author for; nothing in this document changes because of it.

### Required checks before every release

| Tool | Purpose |
| --- | --- |
| EPUBCheck | Structural / schema validity. Must be clean. |
| Ace by DAISY | Accessibility audit. Must be clean. |
| Kindle Previewer 3 | Render in **both** tablet and e-ink modes. |
| Thorium / Readium | Reference EPUB 3 rendering. |

Manual device/app pass: Kindle e-ink (most restrictive), Kobo (older, quirky engine),
Apple Books (most capable). Surviving Kindle *and* Kobo means surviving everywhere.

---

## 2. What we do not control

Assume the reader overrides all of these, in any combination:

font family, font size, line-height, margins, justification, hyphenation, page size,
colour scheme (dark mode), publisher-styles toggle.

Every page must remain readable under any combination of the above.

---

## 3. CSS discipline

**Do**

- Relative units only for type and spacing: `em`, `rem`, `%`.
- Unitless `line-height`.
- Always pair `color` with `background-color` — setting one without the other is the single
  biggest cause of unreadable-in-dark-mode reports.
- Write both legacy and modern break properties:
  ```css
  page-break-before: always;
  break-before: page;
  ```
- Keep body left/right margins at `0`; the reading system supplies its own.
- Treat flexbox and grid as **progressive enhancement only**. Kindle flattens them; the
  flattened result must still be correct.

**Do not**

- `px` for anything except hairline borders.
- Absolute or fixed positioning.
- CSS multi-column layout.
- Viewport units (`vw`, `vh`).
- Floats, flex or grid for load-bearing layout.
- Set a body `font-family` (monospace for code is the only exception).

---

## 4. Tables — the primary risk area

Choose the highest option on this list that the content allows:

1. **Make the table genuinely narrow** — ≤4 columns, short cell contents, no nesting,
   minimal `colspan`/`rowspan`.
2. **Restructure into heading + definition list per row.** Best result on a 6" screen and
   best for accessibility.
3. **Split one wide table into several narrow ones** along a logical axis.
4. **Image of the table**, with the full data repeated in `<figcaption>` or an appendix.
   Genuine last resort.

Mandatory markup and CSS for every table:

```html
<div class="table-wrap">
  <table>
    <caption>Caption is required.</caption>
    <thead>
      <tr><th scope="col">…</th><th scope="col">…</th></tr>
    </thead>
    <tbody>
      <tr><th scope="row">…</th><td>…</td></tr>
    </tbody>
  </table>
</div>
```

```css
.table-wrap { overflow-x: auto; }          /* helps Apple/Kobo, ignored by Kindle */
table       { width: 100%; table-layout: auto; }
th, td      { overflow-wrap: break-word; }
col         { /* percentage widths only — never px */ }
```

---

## 5. Images and figures

- `max-width: 100%; height: auto;` on **every** image, without exception.
- Cap the longest side at ~1600 px, JPEG quality ≈80. Larger files do not improve
  rendering and strain e-ink memory.
- Always `<figure>` + `<figcaption>` + meaningful `alt`. No essential text baked into a
  bitmap.
- Rasterise complex SVG. Simple line art may stay SVG, but test it on Kobo.
- Review every diagram **desaturated** — e-ink is greyscale. Line weights ≥2 px at final
  resolution; no small labels.
- Full-page plates get their own page with an explicit page break. Never floated into text.

---

## 6. Lists

- Maximum two levels of nesting.
- Default markers only. Custom `list-style-type` and `list-style-image` are stripped or
  mangled by several readers.
- Meaning must never depend on exact indentation.

---

## 7. Code blocks and monospace

```css
pre, code {
  white-space: pre-wrap;
  overflow-wrap: break-word;
  font-family: monospace;
}
```

Without `pre-wrap`, long lines are clipped on narrow screens. Keep source lines short
enough (~64 chars) that wrapping is cosmetic rather than destructive.

---

## 8. Embedded fonts

- Embed only when the typeface carries meaning. Readers override anyway.
- Subset aggressively.
- Ship **OTF/TTF**, not WOFF2 (patchier support).
- Always declare a full fallback stack.

---

## 9. Structure and accessibility metadata

Not optional: the **European Accessibility Act** applies to ebooks sold in the EU, so this
is a legal requirement, not a courtesy.

- Clean heading hierarchy, no skipped levels, one `<h1>` per content document.
- Proper EPUB 3 nav document, **plus** an NCX for older devices.
- Semantic `epub:type` / ARIA roles on front matter, chapters, notes.
- In the OPF, include:
  - `schema:accessMode`
  - `schema:accessModeSufficient`
  - `schema:accessibilityFeature`
  - `schema:accessibilityHazard`
  - `schema:accessibilitySummary` (human-readable prose)
- Language declared on `<html lang>` / `xml:lang`; mark inline language changes.

---

## 10. Escape hatch

For genuinely print-dependent material — a 12-column reference table, a wide schematic —
ship a **companion PDF** and link to it from the EPUB. Do not mutilate the EPUB's reflowable
structure to accommodate content that fundamentally needs a fixed page.

---

## 11. Pre-release checklist

- [ ] EPUBCheck clean
- [ ] Ace by DAISY clean
- [ ] Kindle Previewer: tablet mode
- [ ] Kindle Previewer: e-ink mode
- [ ] Apple Books, Kobo, Thorium spot-check
- [ ] Dark mode: no invisible text anywhere
- [ ] Largest reader font size: no clipped tables, no overflow
- [ ] Publisher styles off: content order and readability intact
- [ ] All diagrams legible in greyscale
- [ ] Every image has `alt`; every table has `<caption>` and scoped headers
- [ ] Accessibility metadata present in OPF
