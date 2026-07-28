// pdf-template.typ — print/PDF styling counterpart to epub-style.css.
//
// scripts/build.py prepends this file's content, verbatim, before the
// pandoc-generated typst body (see scripts/pdf-filter.lua for how that body
// gets its color-coded box/lead/note/glossary/criteria markup: pandoc's
// typst writer has no idea what a "box" or "crit-timing" class means and
// drops it silently, so the filter rewrites those into calls to the
// functions defined below).
//
// Unlike the EPUB, a PDF page is a fixed medium the reader can't
// override — so, unlike epub-style.css, this file *does* set a body
// font-family and page size/numbering (FORMATTING.md's "reader overrides
// everything" rule is specifically about reflowable formats).

#let accent-blue = rgb("#4a7fc1")
#let accent-green = rgb("#3f9d63")

#set text(font: "Literata", size: 10pt, lang: "sl")
#set par(justify: true, leading: 0.65em)
#set page(
  paper: "a5",
  margin: (top: 22mm, bottom: 20mm, left: 18mm, right: 18mm),
  header: context {
    let page-num = here().page()
    if page-num > 1 {
      let chapters = query(heading.where(level: 1).before(here()))
      if chapters.len() > 0 {
        align(center)[
          #text(size: 8pt, style: "italic", tracking: 0.5pt)[
            #upper(chapters.last().body)
          ]
        ]
      }
    }
  },
  footer: context {
    let page-num = here().page()
    if page-num > 1 {
      align(center)[#text(size: 9pt)[#counter(page).display()]]
    }
  },
)

// Headings share the epub's Literata-bold-everywhere treatment; a
// chapter (h1) is also a natural place to start a fresh printed page,
// which the EPUB doesn't need (pandoc's --split-level already gives it
// one XHTML file per chapter) but a paginated PDF does.
#show heading: set text(font: "Literata", weight: "bold")
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  v(4mm)
  text(size: 18pt)[#it.body]
  v(8mm)
}
#show heading.where(level: 2): it => { v(2mm); text(size: 14pt)[#it.body]; v(2mm) }
#show heading.where(level: 3): it => { v(1.5mm); text(size: 12pt)[#it.body]; v(1.5mm) }
#show heading.where(level: 4): it => { v(1mm); text(size: 10.5pt)[#it.body]; v(1mm) }
#show heading.where(level: 5): it => { v(1mm); text(size: 10pt)[#it.body]; v(1mm) }

// Images: same "never wider than the text column" rule as epub's
// `img { max-width: 100% }`. A fixed page has no dark mode to break, so
// unlike the epub there is nothing else to account for here.
#set image(width: 100%)
#show figure.caption: it => text(size: 8.5pt, style: "italic")[#it.body]

// Tables: light header shading + hairline borders, mirroring
// epub-style.css's th/td rules. table.header's own row(s) get the
// shading; column widths are left to typst's auto layout, same as the
// epub CSS's `table-layout: auto`.
// `fill` is a table/cell-level property applied to the whole cell box
// *before* inset is applied on top, so — unlike wrapping the cell's
// content in a rect — this shades all the way out to the cell's own
// padding and border, not just the text's own bounding box.
#set table(
  stroke: 0.4pt + rgb("#999999"),
  inset: 5pt,
  fill: (x, y) => if y == 0 { rgb("#eeeeee") } else { none },
)
#show table.cell: it => {
  if it.y == 0 {
    set text(weight: "bold", size: 8.5pt)
    it
  } else {
    set text(size: 8.5pt)
    it
  }
}

// ---- callout boxes (::: box / blockquote note / blockquote lead) ----
// Colors match epub-style.css's light-mode palette (the PDF has no dark
// mode to give a second palette for).
#let book_box(body) = block(
  fill: rgb("#f3f3f3"),
  stroke: 0.5pt + rgb("#999999"),
  inset: (x: 3mm, y: 2mm),
  radius: 1pt,
  width: 100%,
  breakable: true,
)[#body]

#let book_note(body) = block(
  fill: rgb("#eaf2fb"),
  stroke: (left: 1.5pt + accent-blue),
  inset: (x: 3mm, y: 1.5mm, left: 2.5mm),
  width: 100%,
  breakable: true,
)[#body]

#let book_lead(body) = block(
  fill: rgb("#eaf7ee"),
  stroke: (left: 1.5pt + accent-green),
  inset: (x: 3mm, y: 1.5mm, left: 2.5mm),
  width: 100%,
  breakable: true,
)[#body]

// ---- glossary (EN/SL term pairs) ----
#let book_glossary(body) = body
#let gloss_en(body) = block(width: 100%, breakable: true)[
  #set par(hanging-indent: 1.4em)
  #body
]
#let gloss_sl(body) = block(width: 100%, breakable: true, inset: (left: 1.4em))[
  #set par(hanging-indent: 1.4em)
  #body
]
#let tag_en(body) = text(fill: accent-blue, weight: "bold")[#body]
#let tag_sl(body) = text(fill: accent-green, weight: "bold")[#body]

// ---- boxed-list titles ----
#let box_title(body) = text(size: 1.15em, weight: "bold")[#body]

// ---- judging-criteria color coding (KRITERIJI chapter) ----
#let crit_timing(body) = text(fill: rgb("#b8860b"))[#body]
#let crit_tehnika(body) = text(fill: rgb("#2e7d32"))[#body]
#let crit_timsko_delo(body) = text(fill: accent-blue)[#body]
#let crit_preostali(body) = text(fill: rgb("#c0392b"))[#body]
#let crit_muzikalicnost(body) = text(fill: rgb("#2c3e70"))[#body]
#let crit_prezentacija(body) = text(fill: rgb("#8e44ad"))[#body]

// ---- "da"/"ne"/"opcijsko" status values (WSDC round-structure table) ----
// Same green/red/amber-as-yellow palette as the crit_* colors above.
#let val_da(body) = text(fill: rgb("#2e7d32"))[#body]
#let val_ne(body) = text(fill: rgb("#c0392b"))[#body]
#let val_opcijsko(body) = text(fill: rgb("#b8860b"))[#body]
