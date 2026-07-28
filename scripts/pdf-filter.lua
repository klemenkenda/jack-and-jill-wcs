--[[
pdf-filter.lua — pandoc Lua filter used only by scripts/build.py's PDF path
(markdown -> typst). Two unrelated jobs live here because both are about
making the same chapter source that was written for the EPUB (raw HTML
tables/figures, class-tagged fenced divs/spans) produce sensible native
Typst markup instead of being silently flattened or stripped:

1. Raw HTML passthrough (tables, figures) is meaningless for a typst
   target, so re-parse each RawBlock's HTML text with pandoc's own HTML
   reader and splice in the resulting native Blocks (Table, Figure, Image
   ...) that the typst writer knows how to render. This only works
   because scripts/build.py disables the `markdown_in_html_blocks`
   extension for this path, which makes the markdown reader hand us each
   HTML block whole (e.g. one RawBlock per <table>...</table>) instead of
   one RawBlock per tag with the cell text parsed as separate paragraphs
   in between.

2. Class-tagged fenced divs/spans (::: box, [Timing]{.crit-timing}, ...)
   are pandoc's *native* markup, but pandoc's typst writer has no idea
   what a "box" or "crit-timing" class means and drops the class
   silently, emitting a bare #block[...] or nothing at all. Known classes
   are rewritten here as calls to the matching function defined in
   pdf-template.typ (#book_box[...], #crit_timing[...], ...), giving the
   PDF the same color-coded callouts/glossary/criteria styling
   epub-style.css gives the EPUB.
]]

-- Cycled by chapter number (1-indexed) for the big chapter-opener numeral;
-- matching text(fill: ...) colors are defined once in pdf-template.typ.
local CHAPTER_COLORS = {
  "#2e7d32", -- green
  "#4a7fc1", -- blue
  "#c9a227", -- gold (a *readable* yellow — flat #ffff00 has almost no
             -- contrast against white paper)
  "#c0392b", -- red
  "#8e44ad", -- violet
}

local DIV_CLASS_FUNCS = {
  box = "book_box",
  glossary = "book_glossary",
  ["gloss-en"] = "gloss_en",
  ["gloss-sl"] = "gloss_sl",
}

local SPAN_CLASS_FUNCS = {
  ["tag-en"] = "tag_en",
  ["tag-sl"] = "tag_sl",
  ["box-title"] = "box_title",
  ["crit-timing"] = "crit_timing",
  ["crit-tehnika"] = "crit_tehnika",
  ["crit-timsko-delo"] = "crit_timsko_delo",
  ["crit-preostali"] = "crit_preostali",
  ["crit-muzikalicnost"] = "crit_muzikalicnost",
  ["crit-prezentacija"] = "crit_prezentacija",
  ["val-da"] = "val_da",
  ["val-ne"] = "val_ne",
  ["val-opcijsko"] = "val_opcijsko",
}

-- The chapter source escapes markdown-significant punctuation even inside
-- raw HTML table cells (e.g. "1\. mesto", so a plain markdown reader
-- wouldn't mistake "1." for an ordered-list marker). With
-- markdown_in_html_blocks *on* (the EPUB path) pandoc's markdown reader
-- parses that text as markdown and resolves the escape for us; disabling
-- it here (see scripts/build.py) hands RawBlock the HTML completely
-- unparsed, backslash and all, so it has to be undone by hand before the
-- HTML reader below ever sees it, or it just becomes literal, visible
-- backslashes.
local function unescape_markdown_punctuation(text)
  return text:gsub("\\(%p)", "%1")
end

function RawBlock(el)
  if el.format == "html" then
    local ok, doc = pcall(pandoc.read, unescape_markdown_punctuation(el.text), "html")
    if ok then
      -- pandoc's filter walk visits each node once; since this content is
      -- being spliced in *after* that walk already passed over this
      -- RawBlock, nothing would otherwise apply Div/Span below to
      -- class-tagged markup living inside a table/figure (e.g. the
      -- colored val-da/val-ne/val-opcijsko cells) unless it's explicitly
      -- re-walked with the same filter functions here.
      return doc.blocks:walk({ Div = Div, Span = Span })
    end
    return {}
  end
end

local function typst_string_literal(s)
  return '"' .. s:gsub("\\", "\\\\"):gsub('"', '\\"') .. '"'
end

-- Chapter openers (level-1 headings) get a full redesign: a big colored
-- numeral + rule instead of an inline "3. " prefix, cycling through
-- CHAPTER_COLORS by chapter number. scripts/build.py bakes that "3. "
-- prefix into the heading text for *both* formats (numbering has to be
-- computed once, identically, for the EPUB and the PDF to agree), so it
-- has to be peeled back off again here, PDF-side only. The extracted
-- number becomes a separate typst function call (#chapter_marker, defined
-- in pdf-template.typ) inserted as a sibling block *before* the heading,
-- rather than folded into the heading's own body — the body is what
-- #outline() shows verbatim, and it shouldn't try to lay out a 56pt
-- numeral inline.
--
-- #outline() still needs *some* number for this chapter's row, though
-- (unlike the running header, it sits next to unnumbered ZAHVALE/VIRI
-- rows, so "no number" reads as a level rather than a stylistic choice).
-- It gets one via typst's own per-heading `numbering` override: passing a
-- constant closure (rather than `#set heading(numbering: ...)` globally,
-- which would also number ZAHVALE/VIRI) puts our own already-computed
-- number in the outline's number column without it also being baked into
-- the heading body text that the in-page show rule reads from.
--
-- chapter_marker/chapter_marker_plain also stash the plain-text title and
-- (for numbered chapters) the chosen color into typst state, which the
-- running header and the h2/h3 color show rules (pdf-template.typ) read
-- back — *not* a `query(heading.where(level: 1).before(here()))`, which
-- was the original approach but turned out to also match #outline()'s own
-- (non-outlined) internal heading for its "Kazalo vsebine" title,
-- clobbering the running header on every chapter's first page.
function Header(el)
  if el.level == 1 then
    if el.content[1] and el.content[1].t == "Str" then
      local num, rest = el.content[1].text:match("^(%d+)%.(.*)$")
      if num then
        local new_content = pandoc.List({})
        local start_idx = 2
        if rest ~= "" then
          new_content:insert(pandoc.Str(rest))
        elseif el.content[2] and el.content[2].t == "Space" then
          start_idx = 3
        end
        for i = start_idx, #el.content do
          new_content:insert(el.content[i])
        end

        local title_text = pandoc.utils.stringify(new_content)
        local color = CHAPTER_COLORS[((tonumber(num) - 1) % #CHAPTER_COLORS) + 1]
        local marker = pandoc.RawBlock("typst", string.format(
          '#chapter_marker("%02d", rgb("%s"), %s)',
          tonumber(num), color, typst_string_literal(title_text)
        ))
        local heading_open = pandoc.RawBlock("typst", string.format(
          '#heading(level: 1, numbering: (..) => "%s.")[', num
        ))
        local heading_close = pandoc.RawBlock("typst", "]")
        return { marker, heading_open, pandoc.Plain(new_content), heading_close }
      end
    end
    -- Unnumbered level-1 heading (front/back matter, e.g. ZAHVALE): still
    -- gets its own page, just no numeral/color/outline number.
    local title_text = pandoc.utils.stringify(el.content)
    local marker = pandoc.RawBlock("typst", string.format(
      "#chapter_marker_plain(%s)", typst_string_literal(title_text)
    ))
    return { marker, el }
  end
  return nil
end

function Div(el)
  for class, func in pairs(DIV_CLASS_FUNCS) do
    if el.classes:includes(class) then
      local out = pandoc.List({ pandoc.RawBlock("typst", "#" .. func .. "[") })
      out:extend(el.content)
      out:insert(pandoc.RawBlock("typst", "]"))
      return out
    end
  end
  return nil
end

function Span(el)
  for class, func in pairs(SPAN_CLASS_FUNCS) do
    if el.classes:includes(class) then
      local out = pandoc.List({ pandoc.RawInline("typst", "#" .. func .. "[") })
      out:extend(el.content)
      out:insert(pandoc.RawInline("typst", "]"))
      return out
    end
  end
  return nil
end

-- A blockquote directly under a heading is a section "lead" sentence
-- (styled green in epub-style.css), everything else is a note/aside
-- (styled blue). Blockquotes carry no attributes of their own, so the
-- distinction can only be made at the Blocks-list level, by looking at
-- what precedes each BlockQuote.
function Blocks(blocks)
  local out = pandoc.List({})
  local prev_was_heading = false
  for _, block in ipairs(blocks) do
    if block.t == "BlockQuote" then
      local func = prev_was_heading and "book_lead" or "book_note"
      out:insert(pandoc.RawBlock("typst", "#" .. func .. "["))
      out:extend(block.content)
      out:insert(pandoc.RawBlock("typst", "]"))
    else
      out:insert(block)
    end
    prev_was_heading = (block.t == "Header")
  end
  return out
end
