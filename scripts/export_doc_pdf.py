#!/usr/bin/env python3
"""Export a docs/*.md file to dist/*.pdf in the Catalyst house style.

Matches dist/PRD.pdf (ReportLab, A4, Helvetica only):
  body #172B4D 9.5pt, muted #5E6C84, H1 #0052CC 15pt Bold, title 22pt Bold,
  code Courier on #F4F5F7, table head #DEEBFF, grid #DFE1E6,
  footer 'Catalyst | <DOC> ...  Page N', running head top-right.

Usage:
  python3 scripts/export_doc_pdf.py docs/TECH_SPEC.md dist/TECH_SPEC.pdf
  python3 scripts/export_doc_pdf.py docs/PRD.md dist/PRD.pdf --footer-left "Catalyst  |  PRD V1.0 -- Final for Build"

The Markdown file remains the source of truth; the PDF is the shareable
snapshot for review. Requires: pip install reportlab pymupdf (verify only).
"""
import argparse
import re
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, Preformatted,
)
from reportlab.lib import colors

NAVY = HexColor("#172B4D")
MUTED = HexColor("#5E6C84")
BLUE = HexColor("#0052CC")
LIGHT_BG = HexColor("#F4F5F7")
BORDER = HexColor("#DFE1E6")
TABLE_HEAD_BG = HexColor("#DEEBFF")
CODE_FG = HexColor("#091E42")
WHITE = colors.white

PAGE_W, PAGE_H = A4
ML = MR = 48.52
MT = 58
MB = 52

RUNNING_HEAD = "Multi-Tenant Feature Management Platform"

# Per-document cover presets (footer label + summary table rows).
# Summary rows mirror the PRD cover table: [label, markdown body].
# Looked up by version (v1/v2, inferred from path) then by stem uppercased.
PRESETS = {
    "v1": {
        "TECH_SPEC": {
            "footer": "Catalyst  |  TECH SPEC V1.0 \u2014 Ready for Build",
            "pdf_title": "TECH SPEC V1 \u2014 Catalyst",
            "summary": [
                ("Stack", "Fastify + Prisma (Node TS) | React Vite SPA | Postgres 16 + Redis 7 | Docker Compose"),
                ("Mode", "Local-first SDK evaluation + server fallback | Simple predictable rules | Auto-provision onboarding"),
                ("Source", "`docs/PRD.md` V1 Final + locked decisions: Fastify/Prisma, Vite, local-first, simple, auto-provision"),
            ],
        },
        "PRD": {
            "footer": "Catalyst  |  PRD V1.0 \u2014 Final for Build",
            "pdf_title": "PRD V1 Final \u2014 Catalyst",
            "summary": [
                ("Participants", "Product Owner/Dev: You; Stakeholders: Faculty, recruiters; Users: Developer, Release Manager"),
                ("Target release", "V1 MVP \u2014 4 weeks from kickoff, localhost + optional live deploy"),
                ("V1 theme", "Deploy once, release gradually: create flag -> target / rollout % per env -> SDK evaluates -> change propagates in <5s -> audit logged"),
            ],
        },
        "USE_CASES": {
            "footer": "Catalyst  |  USE CASES V1.0 \u2014 Ready for Build",
            "pdf_title": "USE CASES V1 \u2014 Catalyst",
            "summary": [
                ("Source", "`docs/PRD.md` V1 Final + `docs/TECH_SPEC.md` V1 Final"),
                ("Scope", "Boolean flags only, dev / staging / prod, JS + Python SDKs, light audit"),
                ("Propagation", "SSE + polling fallback, p95 < 5s kill propagation"),
            ],
        },
        "POC": {
            "footer": "Catalyst  |  POC V1.0 \u2014 Draft for 2-day build",
            "pdf_title": "POC V1 \u2014 Catalyst",
            "summary": [
                ("Goal", "Prove toggle -> SDK sees it in <5s via SSE -> evaluation sticky"),
                ("Gateway", "Express, in-memory flag, SSE /stream + polling fallback"),
                ("Source", "`docs/PRD.md` V1, `docs/TECH_SPEC.md` V1, `docs/USE_CASES.md` V1"),
            ],
        },
    },
    "v2": {
        "TECH_SPEC": {
            "footer": "Catalyst  |  TECH SPEC V2.0 \u2014 Ready for Build",
            "pdf_title": "TECH SPEC V2 \u2014 Catalyst",
            "summary": [
                ("Stack", "Fastify + Prisma (Node TS) | React Vite SPA | Postgres 16 | Docker Compose | JS + Python SDKs"),
                ("Mode", "Fetch-on-load SDK evaluation + server fallback | Simple predictable rules | Auto-provision onboarding"),
                ("Source", "`docs/v2/PRD.md` V1.1 + locked decisions: fetch-on-load, no SSE, no polling"),
            ],
        },
        "PRD": {
            "footer": "Catalyst  |  PRD V2.0 \u2014 Final for Build",
            "pdf_title": "PRD V2 Final \u2014 Catalyst",
            "summary": [
                ("Participants", "Product Owner/Dev: You; Stakeholders: Faculty, recruiters; Users: Developer, Release Manager"),
                ("Target release", "V2 MVP \u2014 4 weeks from kickoff, localhost + optional live deploy"),
                ("V2 theme", "Deploy once, release gradually: create flag -> target / rollout % per env -> SDK evaluates on load -> change reflected on next refresh -> audit logged"),
            ],
        },
        "USE_CASES": {
            "footer": "Catalyst  |  USE CASES V2.0 \u2014 Ready for Build",
            "pdf_title": "USE CASES V2 \u2014 Catalyst",
            "summary": [
                ("Source", "`docs/v2/PRD.md` V1.1 + `docs/v2/TECH_SPEC.md` V2.0"),
                ("Scope", "Boolean flags only, dev / staging / prod, JS + Python SDKs, light audit. Fetch-on-load only."),
                ("Propagation", "No SSE, no polling. SDK fetches on init; toggle reflected on next load/refresh."),
            ],
        },
        "POC": {
            "footer": "Catalyst  |  POC V2.0 \u2014 Draft for 2-day build",
            "pdf_title": "POC V2 \u2014 Catalyst",
            "summary": [
                ("Goal", "Prove toggle -> SDK picks it up on next load -> evaluation sticky -> offline never crashes"),
                ("Gateway", "Express, in-memory flag, /bootstrap with ETag/304, no SSE"),
                ("Source", "`docs/v2/PRD.md`, `docs/v2/TECH_SPEC.md`, `docs/v2/USE_CASES.md`"),
            ],
        },
    },
}


def ascii_normalize(s: str) -> str:
    # Box-drawing + arrows -> ascii (Type1 WinAnsi lacks these glyphs).
    # PRD.pdf shows '->' for arrows, so mirror that everywhere.
    s = s.replace("\u2192", "->").replace("\u2190", "<-").replace("→", "->").replace("←", "<-")
    s = s.replace("±", "+/-")
    # Symbols outside WinAnsi/Type1 coverage -> ascii (else ReportLab falls back to Symbol font)
    s = s.replace("≈", "~").replace("≤", "<=").replace("≥", ">=").replace("×", "x").replace("→", "->")
    tbl = str.maketrans({
        "\u2500": "-", "\u2501": "-", "\u2502": "|", "\u2503": "|",
        "\u250c": "+", "\u250d": "+", "\u2510": "+", "\u2511": "+",
        "\u2514": "+", "\u2515": "+", "\u2518": "+", "\u2519": "+",
        "\u251c": "+", "\u2524": "+", "\u252c": "+", "\u2534": "+",
        "\u253c": "+", "\u2574": "-", "\u2576": "-",
    })
    return s.translate(tbl)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_inline(s: str) -> str:
    """Convert a small markdown subset (bold, `code`) to ReportLab HTML."""
    s = ascii_normalize(s)
    s = esc(s)
    parts: list[str] = []

    def sub_code(m: re.Match) -> str:
        parts.append(m.group(1))
        return f"\x00{len(parts) - 1}\x00"

    s = re.sub(r"`([^`]+?)`", sub_code, s)
    s = re.sub(r"\*\*([^*]+?)\*\*", r"<b>\1</b>", s)

    def restore(m: re.Match) -> str:
        raw = parts[int(m.group(1))]
        return f'<font face="Courier" color="#172B4D" backColor="#F4F5F7">{raw}</font>'

    return re.sub("\x00(\\d+)\x00", restore, s)


sTitle = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=22, leading=26,
                        textColor=NAVY, alignment=TA_LEFT, spaceAfter=6)
sEyebrow = ParagraphStyle("Eyebrow", fontName="Helvetica", fontSize=10, leading=13,
                          textColor=MUTED, spaceAfter=2)
sMeta = ParagraphStyle("Meta", fontName="Helvetica", fontSize=10, leading=13.5,
                       textColor=MUTED, spaceAfter=1)
sBody = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5, leading=13.5,
                       textColor=NAVY, spaceBefore=3, spaceAfter=3)
sBullet = ParagraphStyle("Bullet", parent=sBody, leftIndent=18, firstLineIndent=0,
                         bulletIndent=6, bulletFontName="Helvetica", bulletFontSize=10,
                         spaceBefore=2, spaceAfter=2)
sStepNum = ParagraphStyle("StepNum", parent=sBody, fontName="Helvetica-Bold",
                         textColor=BLUE, alignment=TA_RIGHT, spaceBefore=0, spaceAfter=0)
sStepText = ParagraphStyle("StepText", parent=sBody, spaceBefore=0, spaceAfter=0)
sH1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15, leading=18,
                     textColor=BLUE, spaceBefore=10, spaceAfter=6, keepWithNext=True)
sH3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=12, leading=14.5,
                     textColor=NAVY, spaceBefore=8, spaceAfter=4, keepWithNext=True)
sLabel = ParagraphStyle("Label", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=NAVY)
sCell = ParagraphStyle("Cell", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=NAVY)
sHeader = ParagraphStyle("Header", parent=sCell, fontName="Helvetica-Bold")
sNote = ParagraphStyle("Note", fontName="Helvetica-Oblique", fontSize=9.5, leading=13,
                       textColor=MUTED, spaceBefore=6, spaceAfter=2)
sCode = ParagraphStyle("Code", fontName="Courier", fontSize=8.5, leading=11,
                       textColor=CODE_FG, backColor=LIGHT_BG, borderPadding=(8, 8, 8))


def code_flowables(lines: list[str]):
    # Chunk long blocks so page splits can occur between chunks.
    out = []
    CH = 32
    for i in range(0, max(1, len(lines)), CH):
        chunk = lines[i:i + CH]
        txt = "\n".join(ascii_normalize(l).rstrip() for l in chunk)
        out.append(Preformatted(txt, sCode, maxLineLength=200))
        if i + CH < len(lines):
            out.append(Spacer(1, 4))
    return out


def split_row(line: str) -> list[str]:
    """Split a markdown table row on pipes, ignoring pipes inside `code`."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, cur, in_code = [], [], False
    for ch in s:
        if ch == "`":
            in_code = not in_code
            cur.append(ch)
        elif ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def is_sep_row(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c) for c in cells)


def parse_md_table(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """Parse a `|...|` line block. Returns (header, rows) or None if invalid."""
    if len(lines) < 2 or not is_sep_row(lines[1]):
        return None
    header = split_row(lines[0])
    rows = [split_row(l) for l in lines[2:]]
    if not rows or any(len(r) != len(header) for r in rows):
        return None
    return header, rows


def make_table(header: list[str], rows: list[list[str]]) -> Table:
    data = [[Paragraph(md_inline(c), sHeader) for c in header]]
    for r in rows:
        data.append([Paragraph(md_inline(c), sCell) for c in r])
    n = len(header)
    avail = PAGE_W - ML - MR
    t = Table(data, colWidths=[avail / n] * n, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEAD_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def make_steps(items: list[tuple[str, str]]) -> Table:
    """Render consecutive `1. ...` items as a vertical step-flow table."""
    rows = [[Paragraph(f"<b>{esc(num)}</b>", sStepNum), Paragraph(md_inline(txt), sStepText)]
            for num, txt in items]
    avail = PAGE_W - ML - MR
    t = Table(rows, colWidths=[30, avail - 30])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BG),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 6),
        ("RIGHTPADDING", (0, 0), (0, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("RIGHTPADDING", (1, 0), (1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_pdf(src: Path, dst: Path, footer_left: str, pdf_title: str,
              summary: list[tuple[str, str]] | None, author: str = "Catalyst") -> int:
    text = src.read_text(encoding="utf-8").splitlines()
    text = [l for l in text if not l.strip().startswith("(End of file")]

    story: list = []
    title_raw = text[0].lstrip("# ").strip() if text and text[0].startswith("#") else src.stem
    idx = 1
    while idx < len(text) and text[idx].strip() == "":
        idx += 1
    cover_meta: list[str] = []
    while idx < len(text):
        line = text[idx].strip()
        if line == "---" or line.startswith("##"):
            break
        if line:
            cover_meta.append(line)
        idx += 1

    story.append(Paragraph(esc(RUNNING_HEAD), sEyebrow))
    story.append(Paragraph(esc(ascii_normalize(title_raw)), sTitle))
    for ml in cover_meta:
        # PRD cover meta is plain muted (bold flattened) — match it.
        plain = ascii_normalize(re.sub(r"\*\*([^*]+?)\*\*", r"\1", ml).replace("`", ""))
        story.append(Paragraph(f'<font color="#5E6C84">{esc(plain)}</font>', sMeta))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceBefore=2, spaceAfter=8))

    if summary:
        def cell_html(md: str) -> Paragraph:
            return Paragraph(md_inline(md), sCell)

        rows = [[Paragraph(f"<b>{esc(k)}</b>", sLabel), cell_html(v)] for k, v in summary]
        table = Table(rows, colWidths=[90, PAGE_W - ML - MR - 90])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), TABLE_HEAD_BG),
            ("BACKGROUND", (1, 0), (1, -1), WHITE),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

    note_html = md_inline(
        f"This PDF was exported from `{src.parent.name}/{src.name}`. "
        "The Markdown file remains the source of truth; this PDF is the "
        "shareable snapshot for review."
    ).replace("#172B4D", "#5E6C84")
    story.append(Paragraph(note_html, sNote))

    i = idx
    in_code = False
    code_buf: list[str] = []
    first_h1_done = False

    def flush_code() -> None:
        nonlocal code_buf
        if code_buf:
            story.extend(code_flowables(code_buf))
            code_buf = []

    num_buf: list[tuple[str, str]] = []

    def flush_steps() -> None:
        nonlocal num_buf
        if num_buf:
            story.append(Spacer(1, 3))
            story.append(make_steps(num_buf))
            story.append(Spacer(1, 3))
            num_buf = []

    while i < len(text):
        line = text[i]
        s = line.strip()
        if s.startswith("```"):
            flush_steps()
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                flush_code()
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        if s == "---":
            flush_steps()
            story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER,
                                    spaceBefore=8, spaceAfter=8))
            i += 1
            continue
        if s.startswith("## "):
            h = s[3:].strip()
            flush_steps()
            if first_h1_done:
                story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER,
                                        spaceBefore=10, spaceAfter=2))
            first_h1_done = True
            story.append(Paragraph(esc(ascii_normalize(h)), sH1))
            i += 1
            continue
        if s.startswith("### "):
            flush_steps()
            story.append(Paragraph(esc(ascii_normalize(s[4:])), sH3))
            i += 1
            continue
        if s.startswith("# "):
            flush_steps()
            i += 1
            continue  # title already rendered as cover
        if s.startswith("|"):
            flush_steps()
            tbl_lines = []
            while i < len(text) and text[i].strip().startswith("|"):
                tbl_lines.append(text[i].strip())
                i += 1
            parsed = parse_md_table(tbl_lines)
            if parsed is None:
                for tl in tbl_lines:  # not a valid table — fall back to body text
                    story.append(Paragraph(md_inline(tl), sBody))
            else:
                header, rows = parsed
                story.append(Spacer(1, 4))
                story.append(make_table(header, rows))
                story.append(Spacer(1, 4))
            continue
        if s.startswith("- "):
            flush_steps()
            story.append(Paragraph(md_inline(s[2:].strip()), sBullet, bulletText="\u2022"))
            i += 1
            continue
        mnum = re.match(r"^(\d+)\.\s+(.*)", s)
        if mnum:
            num_buf.append((mnum.group(1), mnum.group(2)))
            i += 1
            continue
        if s == "":
            if not num_buf:  # blank lines inside a step list don't break it
                story.append(Spacer(1, 3))
            i += 1
            continue
        para_lines = [line.strip()]
        j = i + 1
        while j < len(text):
            lj = text[j]
            sj = lj.strip()
            if (sj == "" or sj.startswith(("## ", "### ", "# ", "- ", "|", "```", "---"))
                    or re.match(r"^\d+\.\s", sj)):
                break
            para_lines.append(sj)
            j += 1
        flush_steps()  # a body paragraph ends any open step list — flush first
        story.append(Paragraph(md_inline(" ".join(para_lines)), sBody))
        i = j

    flush_steps()
    flush_code()

    def on_page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(ML, 30, footer_left)
        canvas.drawRightString(PAGE_W - MR, 30, f"Page {doc.page}")
        if doc.page >= 2:
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(PAGE_W - MR, PAGE_H - 30, RUNNING_HEAD)
        canvas.restoreState()

    doc = BaseDocTemplate(str(dst), pagesize=A4, leftMargin=ML, rightMargin=MR,
                          topMargin=MT, bottomMargin=MB, title=pdf_title, author=author)
    frame = Frame(ML, MB, PAGE_W - ML - MR, PAGE_H - MT - MB, id="main")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])
    doc.build(story)
    return doc.page


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export docs/*.md to dist/*.pdf (Catalyst style).")
    ap.add_argument("src", help="Source markdown, e.g. docs/TECH_SPEC.md")
    ap.add_argument("dst", help="Output PDF, e.g. dist/TECH_SPEC.pdf")
    ap.add_argument("--footer-left", default=None)
    ap.add_argument("--pdf-title", default=None)
    ap.add_argument("--author", default="Catalyst")
    args = ap.parse_args(argv)

    src = Path(args.src)
    dst = Path(args.dst)
    if not src.exists():
        print(f"error: source not found: {src}", file=sys.stderr)
        return 1
    version = "v2" if "v2" in src.parts else "v1"
    preset = PRESETS.get(version, {}).get(src.stem.upper(), {})
    footer = args.footer_left or preset.get("footer", f"Catalyst  |  {src.stem}")
    title = args.pdf_title or preset.get("pdf_title", src.stem)
    summary = preset.get("summary")

    dst.parent.mkdir(parents=True, exist_ok=True)
    pages = build_pdf(src, dst, footer, title, summary, author=args.author)
    print(f"Wrote {dst} pages={pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
