"""Render the two required submission notes as print-friendly PDFs.

The Markdown files remain the editable source of truth. This script only
formats their existing words; it does not generate or rewrite Prompt history.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
FONT_LIGHT = Path("/System/Library/Fonts/STHeiti Light.ttc")
FONT_MEDIUM = Path("/System/Library/Fonts/STHeiti Medium.ttc")
INK = colors.HexColor("#20343E")
MUTED = colors.HexColor("#61747A")
ACCENT = colors.HexColor("#9B7144")


def register_fonts() -> None:
    if not FONT_LIGHT.exists() or not FONT_MEDIUM.exists():
        raise RuntimeError("缺少 macOS STHeiti 字体；请在有中文字体的环境导出 PDF")
    pdfmetrics.registerFont(TTFont("STHeiti", str(FONT_LIGHT), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("STHeiti-Medium", str(FONT_MEDIUM), subfontIndex=0))
    pdfmetrics.registerFontFamily(
        "STHeiti", normal="STHeiti", bold="STHeiti-Medium",
    )


def markup(value: str) -> str:
    escaped = html.escape(value.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`([^`]+)`", r'<font color="#795B38">\1</font>', escaped)
    return escaped


def styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="STHeiti", textColor=INK, alignment=TA_LEFT, wordWrap="CJK")
    return {
        "title": ParagraphStyle(
            "DocumentTitle", **base, fontSize=18, leading=27,
            spaceBefore=7 * mm, spaceAfter=8 * mm,
        ),
        "section": ParagraphStyle(
            "PromptHeading", **(base | {"fontName": "STHeiti-Medium"}), fontSize=11,
            leading=17, spaceBefore=5 * mm, spaceAfter=2.5 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", **base, fontSize=9.7, leading=16.2, spaceAfter=3.4 * mm,
        ),
        "note": ParagraphStyle(
            "Note", **(base | {"textColor": MUTED}), fontSize=9.2, leading=15.5,
            leftIndent=4 * mm, spaceBefore=2 * mm, spaceAfter=3 * mm,
        ),
    }


def flowables(markdown: str, *, prompt_log: bool = False) -> list:
    style = styles()
    blocks = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(Paragraph(markup(line[2:]), style["title"]))
        elif re.match(r"^\d+\.\s", line):
            if prompt_log and line.startswith("4. "):
                blocks.append(PageBreak())
            blocks.append(Paragraph(markup(line), style["section"]))
        elif line.startswith(">"):
            blocks.append(Paragraph(markup(line[1:]), style["note"]))
        else:
            blocks.append(Paragraph(markup(line), style["body"]))
    blocks.append(Spacer(1, 2 * mm))
    return blocks


def page_furniture(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D9DFDD"))
    canvas.setLineWidth(0.6)
    canvas.line(24 * mm, height - 19 * mm, width - 24 * mm, height - 19 * mm)
    canvas.setFont("STHeiti-Medium", 7.8)
    canvas.setFillColor(ACCENT)
    canvas.drawString(24 * mm, height - 15 * mm, "AI PANEL STUDIO  /  SUBMISSION NOTES")
    canvas.setFont("STHeiti", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(24 * mm, 16 * mm, "2026-09-24  ·  AI 圆桌讨论 Web App MVP")
    canvas.drawRightString(width - 24 * mm, 16 * mm, f"{document.page}")
    canvas.restoreState()


def render(source: Path, target: Path) -> None:
    document = SimpleDocTemplate(
        str(target), pagesize=A4, leftMargin=24 * mm, rightMargin=24 * mm,
        topMargin=24 * mm, bottomMargin=23 * mm, title=source.stem,
        author="AI Panel Studio",
    )
    document.build(
        flowables(source.read_text(encoding="utf-8"), prompt_log=source.name == "prompt-log.md"),
        onFirstPage=page_furniture, onLaterPages=page_furniture,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导出提交用 Prompt 与工作流 PDF")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "submission")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    register_fonts()
    for source_name, output_name in (
        ("prompt-log.md", "prompt-log.pdf"),
        ("workflow.md", "workflow.pdf"),
    ):
        source = ROOT / "docs" / source_name
        target = args.output / output_name
        render(source, target)
        print(target)


if __name__ == "__main__":
    main()
