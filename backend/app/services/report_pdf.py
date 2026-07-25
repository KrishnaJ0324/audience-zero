"""Producer report PDF (reportlab). Deterministic — no network, no matplotlib.

Header, producer summary, key metrics, the predicted retention curve drawn
straight from the arrays, top diagnostics, the chosen revision, and the required
AI-audio disclosure footer.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..contracts import AnalysisRun

INK = colors.HexColor("#201d17")
MUTED = colors.HexColor("#857b66")
DANGER = colors.HexColor("#ce381d")
OK = colors.HexColor("#2f6a4b")
RULE = colors.HexColor("#c9bfa8")
PAPER = colors.HexColor("#f3ede0")


class RetentionCurve(Flowable):
    """Draws the aggregate engagement (0..100) and predicted retention (0..1)
    across beats, marking the weakest beat."""

    def __init__(self, run: AnalysisRun, width: float, height: float = 150):
        super().__init__()
        self.run = run
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        v = self.run.verdict
        if not v or not v.aggregate_curve:
            return
        w, h = self.width, self.height
        pad_l, pad_b, pad_t = 24, 18, 10
        plot_w = w - pad_l - 6
        plot_h = h - pad_b - pad_t
        n = len(v.aggregate_curve)

        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        for frac in (0, 0.5, 1.0):
            y = pad_b + plot_h * frac
            c.line(pad_l, y, pad_l + plot_w, y)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 6)
            c.drawRightString(pad_l - 4, y - 2, str(int(frac * 100)))

        def xy(i, val01):
            x = pad_l + (plot_w * (i / max(n - 1, 1)))
            y = pad_b + plot_h * val01
            return x, y

        # weakest beat marker
        wx, _ = xy(v.weakest_beat, 0)
        c.setStrokeColor(DANGER)
        c.setDash(2, 2)
        c.line(wx, pad_b, wx, pad_b + plot_h)
        c.setDash()

        def polyline(vals01, color, width):
            c.setStrokeColor(color)
            c.setLineWidth(width)
            pts = [xy(i, val) for i, val in enumerate(vals01)]
            for a, b in zip(pts, pts[1:]):
                c.line(a[0], a[1], b[0], b[1])

        polyline([x / 100.0 for x in v.aggregate_curve], INK, 1.6)
        if v.retention_curve:
            polyline(v.retention_curve, OK, 1.2)

        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6)
        for i in range(n):
            x, _ = xy(i, 0)
            c.drawCentredString(x, 4, f"B{i + 1}")


def build_pdf(run: AnalysisRun, summary_text: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"Audience Zero — {run.episode_title}",
    )
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=INK, fontSize=22, spaceAfter=2)
    kicker = ParagraphStyle("kicker", parent=ss["Normal"], textColor=MUTED, fontSize=8,
                            fontName="Helvetica", spaceAfter=10)
    body = ParagraphStyle("body", parent=ss["Normal"], textColor=INK, fontSize=10.5, leading=15)
    label = ParagraphStyle("label", parent=ss["Normal"], textColor=MUTED, fontSize=8,
                           fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4)

    v = run.verdict
    provider = run.run_manifest.provider if run.run_manifest else "mock"
    story: list = [
        Paragraph("Audience Zero — Predictive Retention Report", h1),
        Paragraph(
            f"{run.episode_title or 'Episode'} · version {run.version_label} · "
            f"run {run.id} · engine: {provider}", kicker),
        Paragraph(summary_text, body),
        Paragraph("KEY METRICS", label),
    ]

    if v:
        binge = round(v.binge_probability * 100)
        conf = run.confidence.label if run.confidence else "—"
        metrics = [
            ["Predicted drop", "Weakest beat", "Binge probability", "Panel confidence"],
            [f"{v.predicted_drop_pct:.0f}%", f"B{v.weakest_beat + 1}", f"{binge}%", conf],
        ]
        t = Table(metrics, colWidths=[1.6 * inch] * 4)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica", 7),
            ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 16),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("TEXTCOLOR", (0, 1), (0, 1), DANGER),
            ("TEXTCOLOR", (1, 1), (-1, 1), INK),
            ("TOPPADDING", (0, 1), (-1, 1), 2),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ]))
        story += [t, Paragraph("PREDICTED RETENTION", label),
                  RetentionCurve(run, doc.width, 150)]

    # diagnostics
    if run.diagnostics:
        story.append(Paragraph("TOP DIAGNOSTICS", label))
        rows = [["Beat", "Issue", "Severity", "Detail"]]
        for d in run.diagnostics[:6]:
            rows.append([f"B{d.beat_index + 1}", d.type, d.severity, d.summary])
        dt = Table(rows, colWidths=[0.5 * inch, 0.9 * inch, 0.8 * inch, 3.8 * inch])
        dt.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(dt)

    # chosen revision
    variant = next((x for x in run.revision_variants if x.status == "accepted"), None) \
        or (run.revision_variants[-1] if run.revision_variants else None)
    if variant:
        story.append(Paragraph("RECOMMENDED REVISION", label))
        story.append(Paragraph(
            f"<b>Beat {variant.beat_index + 1}</b> ({variant.target}) — "
            f"{variant.change_rationale}", body))

    story += [
        Spacer(1, 18),
        Paragraph(
            "AI-audio disclosure: all spoken audio in this analysis is AI-generated "
            "(synthetic voices — no real person was cloned). Predictions are cheap "
            "directional screening, not ground truth.",
            ParagraphStyle("disc", parent=ss["Normal"], textColor=MUTED, fontSize=7.5,
                           leading=11, borderPadding=6)),
    ]

    doc.build(story)
    return buf.getvalue()
