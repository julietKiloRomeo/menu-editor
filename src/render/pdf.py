"""Render the menu markdown as a PDF for devices without browser printing."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def render_pdf(markdown: str) -> bytes:
    """Make a readable, selectable-text PDF of the same menu as the preview."""
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=29, spaceAfter=12)
    heading = ParagraphStyle(
        "heading", fontName="Helvetica-Bold", fontSize=16, leading=20,
        spaceBefore=10, spaceAfter=5, keepWithNext=True,
    )
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=16, textColor=colors.black)
    story = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), heading))
        elif line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), title))
        elif line.startswith("- "):
            story.append(Paragraph("• " + escape(line[2:]), body))
        elif line:
            story.append(Paragraph(escape(line), body))
        else:
            story.append(Spacer(1, 4))
    document.build(story)
    return output.getvalue()
