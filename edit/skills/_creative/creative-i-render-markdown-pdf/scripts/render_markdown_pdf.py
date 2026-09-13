#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "reportlab==4.2.5",
# ]
# ///
"""Render a compact Markdown document as a black-background vector PDF."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib.colors import black, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Spacer,
)


PLACEHOLDER_RE = re.compile(
    r"\[(?:[^\]]*(?:insert|full legal name|entity)[^\]]*|tbd|to be completed)\]",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
RULE_RE = re.compile(r"^\s*(?:\*{3,}|-{3,})\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Markdown source")
    parser.add_argument("output", type=Path, help="Destination PDF")
    parser.add_argument("--title", help="Optional first-page title override")
    parser.add_argument(
        "--blank-placeholders",
        action="store_true",
        help="Render bracketed drafting fields as blank lines",
    )
    parser.add_argument(
        "--embedded-attachment",
        action="store_true",
        help="Allow an embedded PDF under the owning context's _obsidian/attachments directory",
    )
    return parser.parse_args()


def find_vault_root(path: Path) -> Path | None:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / ".git").exists() and (parent / "_system").is_dir():
            return parent
    return None


def validate_output_location(
    input_path: Path,
    output_path: Path,
    embedded_attachment: bool,
) -> None:
    vault_root = find_vault_root(input_path)
    if vault_root is None:
        return

    resolved_output = output_path.resolve()
    if not resolved_output.is_relative_to(vault_root):
        return

    output_relative = resolved_output.relative_to(vault_root)
    if output_relative.parts[0] in {"tmp", "output"}:
        raise ValueError("Do not create top-level tmp or output folders in the Vault")

    source_relative = input_path.resolve().relative_to(vault_root)
    owner = source_relative.parts[0]
    attachment_root = (vault_root / owner / "_obsidian" / "attachments").resolve()
    if embedded_attachment and not resolved_output.is_relative_to(attachment_root):
        raise ValueError(
            "Embedded Vault PDFs must be saved under the source's owning attachment directory: "
            f"{attachment_root}"
        )
    if not embedded_attachment and "_obsidian" in output_relative.parts:
        raise ValueError(
            "Standalone Vault PDFs cannot be stored under _obsidian; save beside the source note"
        )


def resolve_font(alias: str, candidates: list[Path], fallback: str) -> str:
    for candidate in candidates:
        path = candidate.expanduser()
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(alias, str(path)))
            return alias
        except Exception:
            continue
    return fallback


def font_names() -> tuple[str, str, str]:
    heading = resolve_font(
        "DarkDocumentHeading",
        [
            Path("~/Library/Fonts/NeueAlteGrotesk-Bold.ttf"),
            Path("~/Library/Fonts/IBMPlexSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ],
        "Helvetica-Bold",
    )
    body = resolve_font(
        "DarkDocumentBody",
        [
            Path("~/Library/Fonts/IBMPlexSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ],
        "Helvetica",
    )
    bold = resolve_font(
        "DarkDocumentBodyBold",
        [
            Path("~/Library/Fonts/IBMPlexSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ],
        "Helvetica-Bold",
    )
    return heading, body, bold


def fit_size(text: str, font: str, preferred: float, width: float, minimum: float) -> float:
    size = preferred
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def normalize_text(text: str, blank_placeholders: bool) -> str:
    text = (
        text.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u00d7", "x")
    )
    if blank_placeholders:
        text = PLACEHOLDER_RE.sub("________________________________", text)
    return text


def inline_markup(text: str, blank_placeholders: bool) -> str:
    text = normalize_text(text, blank_placeholders)
    tokens: list[str] = []

    def protect(value: str) -> str:
        tokens.append(value)
        return f"@@TOKEN{len(tokens) - 1}@@"

    text = re.sub(
        r"\[\[([^\]|]+)\|([^\]]+)\]\]",
        lambda match: protect(html.escape(match.group(2))),
        text,
    )
    text = re.sub(
        r"\[\[([^\]]+)\]\]",
        lambda match: protect(html.escape(match.group(1))),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: protect(
            f'<link href="{html.escape(match.group(2), quote=True)}" color="#FFFFFF">'
            f'<u>{html.escape(match.group(1))}</u></link>'
        ),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    for index, token in enumerate(tokens):
        text = text.replace(f"@@TOKEN{index}@@", token)
    return text


def styles(body_font: str, bold_font: str, heading_font: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "DarkBody",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=9.2,
            leading=13.2,
            textColor=white,
            alignment=TA_LEFT,
            spaceAfter=7,
            allowWidows=0,
            allowOrphans=0,
        ),
        "lead": ParagraphStyle(
            "DarkLead",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=11,
            leading=15,
            textColor=white,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "DarkH2",
            parent=sample["Heading2"],
            fontName=heading_font,
            fontSize=16,
            leading=18,
            textColor=white,
            spaceBefore=11,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "DarkH3",
            parent=sample["Heading3"],
            fontName=bold_font,
            fontSize=10.5,
            leading=13,
            textColor=white,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "DarkBullet",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=9.1,
            leading=13,
            textColor=white,
            leftIndent=0,
            firstLineIndent=0,
            spaceAfter=3,
        ),
        "signature": ParagraphStyle(
            "DarkSignature",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=9.5,
            leading=15,
            textColor=white,
            spaceAfter=9,
        ),
    }


def parse_markdown(source: str, style_map: dict[str, ParagraphStyle], blank_placeholders: bool):
    lines = source.splitlines()
    title = "Document"
    first_heading_index: int | None = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            title = normalize_text(match.group(2), blank_placeholders)
            first_heading_index = index
            break

    story = []
    paragraph_lines: list[str] = []
    bullets: list[str] = []
    seen_section = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        raw = " ".join(part.strip() for part in paragraph_lines)
        style = style_map["lead"] if not seen_section else style_map["body"]
        if raw.startswith("For ") or raw.startswith("Name:") or raw.startswith("Signature:"):
            style = style_map["signature"]
        story.append(Paragraph(inline_markup(raw, blank_placeholders), style))
        paragraph_lines = []

    def flush_bullets() -> None:
        nonlocal bullets
        if not bullets:
            return
        items = [
            ListItem(
                Paragraph(inline_markup(item, blank_placeholders), style_map["bullet"]),
                leftIndent=10,
            )
            for item in bullets
        ]
        story.append(
            ListFlowable(
                items,
                bulletType="bullet",
                start="-",
                bulletFontName=style_map["body"].fontName,
                bulletFontSize=5.5,
                bulletColor=white,
                leftIndent=13,
                bulletOffsetY=1.5,
                spaceAfter=6,
            )
        )
        bullets = []

    for index, line in enumerate(lines):
        if index == first_heading_index:
            continue
        heading = HEADING_RE.match(line)
        bullet = BULLET_RE.match(line)
        if not line.strip():
            flush_paragraph()
            flush_bullets()
            continue
        if RULE_RE.match(line):
            flush_paragraph()
            flush_bullets()
            story.append(Spacer(1, 2))
            story.append(HRFlowable(width="100%", thickness=0.6, color=white, spaceBefore=4, spaceAfter=8))
            continue
        if heading:
            flush_paragraph()
            flush_bullets()
            level = len(heading.group(1))
            if level <= 2:
                seen_section = True
                if heading.group(2).strip().lower() == "signatures":
                    story.append(CondPageBreak(58 * mm))
                story.append(Paragraph(inline_markup(heading.group(2), blank_placeholders), style_map["h2"]))
            else:
                story.append(Paragraph(inline_markup(heading.group(2), blank_placeholders), style_map["h3"]))
            continue
        if bullet:
            flush_paragraph()
            bullets.append(bullet.group(1))
            continue
        flush_bullets()
        paragraph_lines.append(line)

    flush_paragraph()
    flush_bullets()
    return title, story


def draw_background(canvas, page_width: float, page_height: float) -> None:
    canvas.saveState()
    canvas.setFillColor(black)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    canvas.restoreState()


def build_pdf(
    input_path: Path,
    output_path: Path,
    title_override: str | None,
    blank_placeholders: bool,
    embedded_attachment: bool,
) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(f"Markdown source not found: {input_path}")
    validate_output_location(input_path, output_path, embedded_attachment)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    heading_font, body_font, bold_font = font_names()
    style_map = styles(body_font, bold_font, heading_font)
    source = input_path.read_text(encoding="utf-8")
    title, story = parse_markdown(source, style_map, blank_placeholders)
    width, height = A4
    left = 16 * mm
    right = 16 * mm
    bottom = 16 * mm

    first_frame = Frame(
        left,
        bottom,
        width - left - right,
        height - bottom - 45 * mm,
        id="first-frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    later_frame = Frame(
        left,
        bottom,
        width - left - right,
        height - bottom - 18 * mm,
        id="later-frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    clean_title = normalize_text((title_override or title).strip(), blank_placeholders)

    def first_page(canvas, doc) -> None:
        draw_background(canvas, width, height)
        canvas.saveState()
        canvas.setFillColor(white)
        title_size = fit_size(clean_title, heading_font, 24, width - left - right, 16)
        canvas.setFont(heading_font, title_size)
        canvas.drawString(left, height - 28 * mm, clean_title)
        draw_footer(canvas, doc.page)
        canvas.restoreState()

    def later_page(canvas, doc) -> None:
        draw_background(canvas, width, height)
        canvas.saveState()
        draw_footer(canvas, doc.page)
        canvas.restoreState()

    def draw_footer(canvas, page_number: int) -> None:
        canvas.setFillColor(white)
        canvas.setFont(body_font, 7.5)
        canvas.drawRightString(width - right, 6 * mm, f"[PAGE {page_number}]")

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=0,
        bottomMargin=bottom,
        title=title,
        subject="Markdown document",
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="first",
                frames=[first_frame],
                onPage=first_page,
                autoNextPageTemplate="later",
            ),
            PageTemplate(id="later", frames=[later_frame], onPage=later_page),
        ]
    )
    doc.build(story)


def main() -> int:
    args = parse_args()
    try:
        build_pdf(
            input_path=args.input,
            output_path=args.output,
            title_override=args.title,
            blank_placeholders=args.blank_placeholders,
            embedded_attachment=args.embedded_attachment,
        )
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"PDF generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
