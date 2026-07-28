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

// Updated once per chapter by #chapter_marker/#chapter_marker_plain
// (scripts/pdf-filter.lua inserts a call to one of those as a sibling
// block right before every level-1 heading) — read by the running header
// below and by the h2/h3 color show rules further down. Deliberately
// *not* `query(heading.where(level: 1).before(here()))`: that also
// matched #outline()'s own internal (non-outlined) heading for its
// "Kazalo vsebine" title, which clobbered the running header with
// "KAZALO VSEBINE" on every chapter's opening page.
#let chapter-title = state("chapter-title", "")
#let current-chapter-color = state("current-chapter-color", rgb("#16232e"))

#set text(font: "Literata", size: 10pt, lang: "sl")
#set par(justify: true, leading: 0.65em)
#set page(
  paper: "a5",
  margin: (top: 22mm, bottom: 20mm, left: 18mm, right: 18mm),
  header: context {
    // Pages 1-2 are the title page and impressum (see title_page/
    // impressum_page below), both of which use their own #page(...) call
    // with header/footer explicitly set to none — this condition is a
    // fallback, not the primary mechanism, in case front matter ever
    // grows without remembering to opt back out here too.
    let page-num = here().page()
    if page-num > 2 {
      let t = chapter-title.get()
      if t != "" {
        align(center)[
          #text(size: 8pt, style: "italic", tracking: 0.5pt)[#upper(t)]
        ]
      }
    }
  },
  footer: context {
    let page-num = here().page()
    if page-num > 2 {
      align(center)[#text(size: 9pt)[#counter(page).display()]]
    }
  },
)

// ---- title page ----
// A full-bleed cover image needs a page with zero margin, different
// from every other page in the book — #page(..)[..] (as opposed to
// #set page(..)) scopes its settings to just the page(s) its content
// spans, so this can override margin/header/footer for one page without
// touching the #set page() rule above that governs the rest of the book.
// Title and the rest of the front-matter text sit in translucent white
// boxes rather than directly on the image, since the cover art has both
// light and busy/colored regions and plain dark text would lose contrast
// against whichever one ends up behind a given corner.
// Every piece of text on the title page shares this one font (Roboto),
// unlike the rest of the book, which is set in Literata throughout.
#let title-font = "Roboto"
#let title-text-color = rgb("#16232e")
#let title-line2-color = rgb("#a8a8a8") // silver, for title-lines' 2nd+ line

// A5 paper is 148mm wide (see #set page(paper: "a5") above); the title
// block is capped at 42% of that.
#let title-max-width = 148mm * 0.42

// `title-lines` is a manual line break (e.g. ("Jack and Jill",
// "tekmovanja v WCS")), rather than automatic wrapping. Each line gets
// its *own* font size so its rendered width comes out to exactly
// title-max-width — i.e. the shorter line is scaled bigger to match, not
// letter-spaced wider — which also caps the whole block at that width by
// construction. measure() (which needs `context`, since width depends on
// how the font actually shapes the text) gives the natural width to
// scale from.
#let title_page(title-lines, author, cover-path) = {
  page(margin: 0pt, header: none, footer: none, fill: white)[
    #place(top + left, image(cover-path, width: 100%, height: 100%, fit: "cover"))
    #place(top + left, dx: 10mm, dy: 12mm)[
      #block(fill: rgb(255, 255, 255, 217), inset: (x: 4mm, y: 3mm), radius: 2pt)[
        #context {
          let probe-size = 22pt
          let mk(t, size, color) = text(font: title-font, size: size, weight: "bold", fill: color)[#t]
          stack(
            spacing: 4.5mm,
            ..title-lines.enumerate().map(((i, line)) => {
              let color = if i == 0 { title-text-color } else { title-line2-color }
              let w = measure(mk(line, probe-size, color)).width
              mk(line, probe-size * (title-max-width / w), color)
            }),
          )
        }
      ]
    ]
    #place(bottom + right, dx: -10mm, dy: -12mm)[
      #block(fill: rgb(255, 255, 255, 217), inset: (x: 4mm, y: 3mm), radius: 2pt)[
        #text(font: title-font, size: 10.5pt, weight: "bold", fill: title-text-color)[#author]
      ]
    ]
  ]
}

// ---- impressum (colophon) page ----
// `isbn` may be "" (no ISBN assigned yet) — the line is only shown when
// one is set, rather than printing an empty "ISBN: " placeholder.
// `city` (not `place`) to avoid shadowing typst's built-in `place()`
// positioning function within this scope.
#let impressum_page(
  title, subtitle, author, publisher, city, year, rights, license,
  cover-credit, version, isbn,
) = {
  page(margin: (top: 22mm, bottom: 20mm, left: 18mm, right: 18mm), header: none, footer: none)[
    #v(1fr)
    #block(
      stroke: 0.6pt + rgb("#999999"),
      inset: (x: 6mm, y: 5mm),
      radius: 2pt,
      width: 100%,
    )[
      #text(size: 12pt, weight: "bold")[#title]
      #linebreak()
      #text(size: 10pt, style: "italic")[#subtitle]
      #v(5mm)
      #text(size: 9pt)[
        #author

        #publisher

        #city, #year

        #v(3mm)
        #(rights). #(license)

        #v(3mm)
        verzija #version

        #if isbn != "" [ISBN: #isbn]

        #v(3mm)
        #text(style: "italic")[#cover-credit]
      ]
    ]
    #v(1fr)
  ]
}

// Headings share the epub's Literata-bold-everywhere treatment; a
// chapter (h1) is also a natural place to start a fresh printed page,
// which the EPUB doesn't need (pandoc's --split-level already gives it
// one XHTML file per chapter) but a paginated PDF does. The page break
// itself, and — for numbered chapters — a big colored numeral above the
// title, come from #chapter_marker/#pagebreak calls that
// scripts/pdf-filter.lua inserts as a sibling block right before each
// level-1 heading; this show rule only lays out the title text itself.
#show heading: set text(font: "Literata", weight: "bold")

// Called from scripts/pdf-filter.lua, once per numbered chapter (not for
// unnumbered front/back matter — see chapter_marker_plain for that).
// Besides drawing the numeral, this is what feeds the running header
// and the h2/h3 color show rules below for the rest of the chapter.
#let chapter_marker(num, color, title) = {
  chapter-title.update(title)
  current-chapter-color.update(color)
  pagebreak(weak: true)
  v(16mm)
  align(center)[
    #text(size: 56pt, weight: "bold", font: "Literata", fill: color)[#num]
    #v(3mm)
    #line(length: 40%, stroke: 1.5pt + color)
  ]
  v(8mm)
}

// Front/back matter (ZAHVALE, VIRI IN LITERATURA, ...): still its own
// page and still updates the running header, just with no numeral and a
// neutral (rather than stale-leftover-chapter) heading color.
#let chapter_marker_plain(title) = {
  chapter-title.update(title)
  current-chapter-color.update(title-text-color)
  pagebreak(weak: true)
}

#show heading.where(level: 1): it => {
  align(center)[#text(size: 19pt)[#it.body]]
  v(8mm)
}
#show heading.where(level: 2): it => context {
  v(2mm); text(size: 14pt, fill: current-chapter-color.get())[#it.body]; v(2mm)
}
#show heading.where(level: 3): it => context {
  v(1.5mm); text(size: 12pt, fill: current-chapter-color.get())[#it.body]; v(1.5mm)
}
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
