"""Shared report layout and entry point for the current jury report.

Optional authoring dependencies, separate from the application runtime:
    uv tool run --from reportlab --with pypdf python scripts/build_report.py
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output/pdf/Rapport_Projet_Pharma.pdf"
INK = colors.HexColor("#142D44")
TEAL = colors.HexColor("#087F8C")
PALE = colors.HexColor("#EDF5F7")
GRAY = colors.HexColor("#536577")
W = A4[0] - 94


def register_fonts():
    candidates = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
    for folder in candidates:
        normal = folder / ("arial.ttf" if folder.name == "Fonts" else "DejaVuSans.ttf")
        bold = folder / ("arialbd.ttf" if folder.name == "Fonts" else "DejaVuSans-Bold.ttf")
        if normal.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("Body", str(normal)))
            pdfmetrics.registerFont(TTFont("BodyBold", str(bold)))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold", italic="Body", boldItalic="BodyBold")
            return
    raise RuntimeError("Install Arial or DejaVu Sans to render French text")


register_fonts()
STYLES = {
    "body": ParagraphStyle("body", fontName="Body", fontSize=10.1, leading=14.5, textColor=INK, spaceAfter=9),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8.4, leading=11.6, textColor=INK, spaceAfter=5),
    "title": ParagraphStyle("title", fontName="BodyBold", fontSize=25, leading=30, textColor=INK, spaceAfter=18),
    "sub": ParagraphStyle("sub", fontName="BodyBold", fontSize=12.5, leading=17, textColor=TEAL, spaceBefore=10, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.6, leading=11.8, textColor=INK),
    "head": ParagraphStyle("head", fontName="BodyBold", fontSize=8.7, leading=12, textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Body", fontSize=8.4, leading=12, textColor=INK,
                           leftIndent=9, rightIndent=9, backColor=PALE, borderPadding=8, spaceAfter=12),
}


def p(text, style="body"):
    return Paragraph(text, STYLES[style])


def plain(text, style="body"):
    return p(escape(str(text)), style)


def code(text):
    return p(escape(text).replace("\n", "<br/>"), "code")


def table(headers, rows, widths=None):
    content = [[plain(v, "head") for v in headers]]
    content += [[plain(v, "cell") for v in row] for row in rows]
    t = Table(content, colWidths=widths or [W / len(headers)] * len(headers), repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEAL),
    ]))
    return t


class Workflow(Flowable):
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = W, 248

    def draw(self):
        c = self.canv
        nodes = [
            ("Question et plan", "Décomposer la demande, préciser les produits"),
            ("Choix des outils", "Recherche, sections, inventaire, glossaire"),
            ("Sélection structurée", "Focus littéraux c1, c2... et identifiants de contextes"),
            ("Revue et contrôles", "Sens examiné par le modèle, provenance vérifiée par le code"),
            ("Extraits ou abstention", "Texte source littéral, synthèses serveur limitées"),
        ]
        for i, (title, subtitle) in enumerate(nodes):
            y = self.height - 44 - i * 49
            c.setFillColor(PALE)
            c.roundRect(7, y, W - 14, 40, 7, fill=1, stroke=0)
            c.setFillColor(TEAL)
            c.setFont("BodyBold", 10)
            c.drawString(19, y + 25, f"{i + 1}. {title}")
            c.setFillColor(INK)
            c.setFont("Body", 8.3)
            c.drawString(19, y + 10, subtitle)
            if i < len(nodes) - 1:
                c.setStrokeColor(TEAL)
                c.line(W / 2, y, W / 2, y - 8)
                c.line(W / 2, y - 8, W / 2 - 3, y - 4)
                c.line(W / 2, y - 8, W / 2 + 3, y - 4)


class ReportDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "title":
            key = f"section-{self.page}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(), key, level=0)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.7)
    canvas.line(47, 45, A4[0] - 47, 45)
    canvas.setFillColor(GRAY)
    canvas.setFont("Body", 8)
    canvas.drawString(47, 31, "Pharma Research Agent | Rapport technique | 13 novembre 2026")
    canvas.drawRightString(A4[0] - 47, 31, str(doc.page))
    if doc.page > 1:
        canvas.setFont("BodyBold", 8)
        canvas.drawString(47, A4[1] - 31, "COMPRENDRE, VÉRIFIER, PRÉSENTER")
    canvas.restoreState()


def main():
    from build_jury_report import main as build_current_report
    build_current_report()


if __name__ == "__main__":
    main()
