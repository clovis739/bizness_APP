
import json
from datetime import datetime
import re
from xml.sax.saxutils import escape
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from app.database import supabase
from app.routers.dashboard import get_current_user # Reusing our secure bouncer!
from app.services.push_notifications import merge_push_token, remove_push_token
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, String, Line

BIZNESS_PRIMARY = colors.HexColor("#143C7D")
BIZNESS_SECONDARY = colors.HexColor("#2E6BDE")
BIZNESS_ACCENT = colors.HexColor("#16A34A")
BIZNESS_WARNING = colors.HexColor("#EA580C")
BIZNESS_MUTED = colors.HexColor("#4A5568")
BIZNESS_BORDER = colors.HexColor("#D6E2FF")
BIZNESS_SURFACE = colors.HexColor("#F5F9FF")
BIZNESS_SOFT = colors.HexColor("#EAF1FF")

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

class PreferencesUpdate(BaseModel):
    notifs: dict
    privacy: dict


class PushTokenRegistration(BaseModel):
    token: str
    platform: str


class PushTokenRemoval(BaseModel):
    token: str


# Normalize mixed values from Supabase into printable text for the report.
def _stringify_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    if value is None:
        return "N/A"
    return str(value)


# Convert raw backend timestamps into a human-friendly export label.
def _format_datetime(value):
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return str(value)


# Keep currency formatting consistent across cards, tables, and visuals.
def _format_currency(value):
    try:
        amount = float(value)
        return f"XAF {amount:,.0f}"
    except Exception:
        return "N/A"


# The ML layer may return decimal probabilities, so normalize them for display.
def _format_probability(value):
    try:
        amount = float(value)
        if amount <= 1:
            amount *= 100
        return f"{amount:.1f}%"
    except Exception:
        return "N/A"


# Escape text before handing it to ReportLab paragraph markup.
def _safe_paragraph(text):
    return escape(_stringify_value(text)).replace("\n", "<br/>")


# Convert markdown-style **bold** content into ReportLab <b> tags.
def _rich_text(text):
    source = _stringify_value(text)
    segments = re.split(r"(\*\*.*?\*\*)", source)
    transformed = []

    for segment in segments:
        if segment.startswith("**") and segment.endswith("**") and len(segment) > 4:
            transformed.append(f"<b>{escape(segment[2:-2])}</b>")
        else:
            transformed.append(escape(segment))

    return "".join(transformed).replace("\n", "<br/>")


# Turn semi-structured recommendation text into clean bullet items.
def _normalise_bullet_items(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.replace("•", "\n").replace(" - ", "\n").replace("; ", "\n")
        return [item.strip(" -\n\t") for item in cleaned.splitlines() if item.strip(" -\n\t")]
    return []


# Clean risk labels that arrive without spaces from the prediction service.
def _clean_risk_label(value):
    text = _stringify_value(value).replace("HighRisk", "High Risk").replace("LowRisk", "Low Risk")
    return text.title()


# Shared section heading helper to keep report sections visually uniform.
def _section_heading(text, style):
    return Paragraph(text, style)


# Reusable two-column metadata table used by overview sections.
def _build_key_value_table(rows):
    table = Table(rows, colWidths=[160, 320], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), BIZNESS_PRIMARY),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, BIZNESS_BORDER),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#B8CCF5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


# Reusable table styling for business and prediction summary lists.
def _build_prediction_table(headers, rows):
    table = Table([headers, *rows], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D9E6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


# Arrange summary cards into a two-column grid for the cover and summary area.
def _build_summary_cards(cards):
    rows = []
    current = []
    for card in cards:
        current.append(card)
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        current.append("")
        rows.append(current)

    table = Table(rows, colWidths=[250, 250], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


# Render a single branded metric card with configurable emphasis color.
def _make_card(title, value, tint, value_color=None):
    value_color = value_color or BIZNESS_PRIMARY
    inner = Table(
        [[title], [value]],
        colWidths=[238],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), tint),
                ("BOX", (0, 0), (-1, -1), 0.8, BIZNESS_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), BIZNESS_MUTED),
                ("TEXTCOLOR", (0, 1), (-1, -1), value_color),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 16),
            ],
        ),
    )
    return inner


# Draw lightweight inline visuals so the PDF has readable snapshots without changing the data.
def _build_metric_visuals(survival_predictions, growth_forecasts):
    latest_survival = survival_predictions[0] if survival_predictions else {}
    latest_growth = growth_forecasts[0] if growth_forecasts else {}

    survival_pct = 0
    try:
        survival_pct = float(latest_survival.get("survival_probability", 0))
        if survival_pct <= 1:
            survival_pct *= 100
    except Exception:
        survival_pct = 0

    growth_rate = 0
    try:
        growth_rate = float(latest_growth.get("growth_rate", 0))
    except Exception:
        growth_rate = 0

    profit_value = 0
    try:
        profit_value = max(0, float(latest_growth.get("predicted_profit_cfa", 0)))
    except Exception:
        profit_value = 0

    drawing = Drawing(520, 150)
    drawing.add(Rect(0, 0, 520, 150, rx=12, ry=12, fillColor=BIZNESS_SURFACE, strokeColor=BIZNESS_BORDER))
    drawing.add(String(18, 112, "Prediction Snapshot", fontName="Helvetica-Bold", fontSize=13, fillColor=BIZNESS_PRIMARY))

    # Survival bar
    drawing.add(String(18, 88, "Survival Probability", fontName="Helvetica-Bold", fontSize=9, fillColor=BIZNESS_MUTED))
    drawing.add(Rect(18, 72, 145, 10, fillColor=colors.HexColor("#DDE8FF"), strokeColor=None))
    drawing.add(Rect(18, 72, max(0, min(145, (survival_pct / 100) * 145)), 10, fillColor=BIZNESS_SECONDARY, strokeColor=None))
    drawing.add(String(170, 73, _format_probability(latest_survival.get("survival_probability")), fontName="Helvetica-Bold", fontSize=10, fillColor=BIZNESS_PRIMARY))

    # Growth bar
    normalized_growth = max(0, min(100, growth_rate if growth_rate > 1 else growth_rate * 100))
    drawing.add(String(18, 48, "Growth Rate", fontName="Helvetica-Bold", fontSize=9, fillColor=BIZNESS_MUTED))
    drawing.add(Rect(18, 32, 145, 10, fillColor=colors.HexColor("#DCFCE7"), strokeColor=None))
    drawing.add(Rect(18, 32, max(0, min(145, (normalized_growth / 100) * 145)), 10, fillColor=BIZNESS_ACCENT, strokeColor=None))
    drawing.add(String(170, 33, _stringify_value(latest_growth.get("growth_rate")), fontName="Helvetica-Bold", fontSize=10, fillColor=BIZNESS_PRIMARY))

    # Profit mini bars
    drawing.add(String(290, 104, "Projected Profit", fontName="Helvetica-Bold", fontSize=9, fillColor=BIZNESS_MUTED))
    drawing.add(String(290, 84, _format_currency(latest_growth.get("predicted_profit_cfa")), fontName="Helvetica-Bold", fontSize=12, fillColor=BIZNESS_PRIMARY))
    base_x = 290
    base_y = 20
    bar_width = 18
    spacing = 10
    profit_scale = max(1.0, profit_value)
    for idx, factor in enumerate([0.35, 0.6, 0.85, 1.0]):
        height = 20 + (profit_scale * factor / profit_scale) * 32
        drawing.add(Rect(base_x + idx * (bar_width + spacing), base_y, bar_width, height, fillColor=BIZNESS_WARNING if idx == 3 else BIZNESS_SECONDARY, strokeColor=None))
    drawing.add(Line(282, 18, 500, 18, strokeColor=BIZNESS_BORDER, strokeWidth=1))
    drawing.add(String(290, 6, "Relative profit trend", fontName="Helvetica", fontSize=8, fillColor=BIZNESS_MUTED))
    return drawing


# Build the first-page hero block and supporting metadata cards.
def _build_cover_block(user, export_type, generated_at):
    hero = Table(
        [
            [Paragraph("BizNess Data Export", ParagraphStyle(
                "HeroTitle",
                fontName="Helvetica-Bold",
                fontSize=26,
                leading=30,
                textColor=colors.white,
                alignment=TA_CENTER,
            ))],
            [Paragraph(
                f"{export_type.title()} report prepared for {_stringify_value(user.get('name'))}",
                ParagraphStyle(
                    "HeroSubtitle",
                    fontName="Helvetica",
                    fontSize=12,
                    leading=16,
                    textColor=colors.HexColor("#E8F1FF"),
                    alignment=TA_CENTER,
                ),
            )],
            [Paragraph(
                f"Generated on {generated_at}",
                ParagraphStyle(
                    "HeroMeta",
                    fontName="Helvetica-Bold",
                    fontSize=10,
                    leading=14,
                    textColor=colors.HexColor("#D6E6FF"),
                    alignment=TA_CENTER,
                ),
            )],
        ],
        colWidths=[520],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BIZNESS_PRIMARY),
                ("LEFTPADDING", (0, 0), (-1, -1), 24),
                ("RIGHTPADDING", (0, 0), (-1, -1), 24),
                ("TOPPADDING", (0, 0), (-1, 0), 22),
                ("TOPPADDING", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.8, BIZNESS_PRIMARY),
            ]
        ),
    )

    support = Table(
        [
            [
                _make_card("Account Owner", _stringify_value(user.get("name")), BIZNESS_SOFT),
                _make_card("Contact Email", _stringify_value(user.get("email")), colors.HexColor("#EEF4FF")),
            ],
            [
                _make_card("Export Type", export_type.title(), colors.HexColor("#ECFDF3"), BIZNESS_ACCENT),
                _make_card("Report Date", generated_at, colors.HexColor("#FFF7ED"), BIZNESS_WARNING),
            ],
        ],
        colWidths=[250, 250],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )

    return [hero, Spacer(1, 18), support, Spacer(1, 6)]


# Add a footer separator and page number to every page of the export.
def _draw_page_footer(canvas, doc):
    canvas.saveState()
    page_width, _ = A4
    canvas.setStrokeColor(BIZNESS_BORDER)
    canvas.line(doc.leftMargin, 24, page_width - doc.rightMargin, 24)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BIZNESS_MUTED)
    canvas.drawString(doc.leftMargin, 12, "BizNess Export")
    canvas.drawRightString(page_width - doc.rightMargin, 12, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# Assemble the full branded PDF using the export payload already prepared by the API route.
def _build_pdf_export(export_data: dict, export_type: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"BizNess Export {export_type.title()}",
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=BIZNESS_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["BodyText"],
        fontSize=11,
        leading=15,
        alignment=TA_CENTER,
        textColor=BIZNESS_MUTED,
        spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=BIZNESS_PRIMARY,
        spaceAfter=10,
        spaceBefore=12,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1F2937"),
    )
    bullet_style = ParagraphStyle(
        "BulletBody",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        leftIndent=14,
        bulletIndent=2,
        spaceBefore=2,
        spaceAfter=2,
        textColor=colors.HexColor("#1F2937"),
    )

    # Shared timestamp used throughout the cover and account summary.
    generated_at = datetime.now().strftime("%b %d, %Y %I:%M %p")
    # Split the export payload into the main report sections.
    user = export_data.get("user", {})
    businesses = export_data.get("businesses", [])
    survival_predictions = export_data.get("survival_predictions", [])
    growth_forecasts = export_data.get("growth_forecasts", [])
    latest_growth_report = growth_forecasts[0].get("full_report") if growth_forecasts else {}
    latest_growth_report = latest_growth_report if isinstance(latest_growth_report, dict) else {}

    story = [
        *_build_cover_block(user, export_type, generated_at),
        Paragraph(
            "This report presents your BizNess account, business portfolio, and prediction activity in a polished export format.",
            subtitle_style,
        ),
        Spacer(1, 10),
    ]

    story.extend(
        [
            _section_heading("Account Overview", section_style),
            _build_key_value_table(
                [
                    ["Field", "Value"],
                    ["Name", _stringify_value(user.get("name"))],
                    ["Email", _stringify_value(user.get("email"))],
                    ["SME ID", _stringify_value(user.get("sme_id"))],
                    ["Export Type", export_type.title()],
                    ["Generated At", generated_at],
                ]
            ),
            Spacer(1, 14),
        ]
    )

    story.extend([
        _section_heading("Export Summary", section_style),
        _build_summary_cards(
            [
                _make_card("Business Profiles", str(len(businesses)), BIZNESS_SOFT),
                _make_card("Survival Predictions", str(len(survival_predictions)), colors.HexColor("#EEF4FF")),
                _make_card("Growth Forecasts", str(len(growth_forecasts)), colors.HexColor("#ECFDF3"), BIZNESS_ACCENT),
                _make_card(
                    "Latest Projected Profit",
                    _format_currency(growth_forecasts[0].get("predicted_profit_cfa")) if growth_forecasts else "N/A",
                    colors.HexColor("#FFF7ED"),
                    BIZNESS_WARNING,
                ),
            ]
        ),
        Spacer(1, 14),
    ])

    if survival_predictions or growth_forecasts:
        story.extend([
            _section_heading("Visual Summary", section_style),
            _build_metric_visuals(survival_predictions, growth_forecasts),
            Spacer(1, 14),
        ])

    if businesses:
        business_rows = [["Business", "Industry", "Region", "Employees"]]
        for item in businesses[:10]:
            business_rows.append(
                [
                    _stringify_value(item.get("name")),
                    _stringify_value(item.get("industry")),
                    _stringify_value(item.get("region")),
                    _stringify_value(item.get("employees")),
                ]
            )
        story.extend(
            [
                _section_heading("Business Portfolio", section_style),
                _build_prediction_table(business_rows[0], business_rows[1:]),
                Spacer(1, 14),
            ]
        )

    if export_type in ["all", "predictions"]:
        # Narrative sections come from the latest generated growth report when available.
        story.extend([
            _section_heading("Prediction Insights", section_style),
            Paragraph(
                "The tables below highlight your most recent survival and growth outputs in a format that is easier to review than raw JSON.",
                body_style,
            ),
            Spacer(1, 10),
        ])

        if survival_predictions:
            # Keep recent survival rows compact so they remain easy to scan in print.
            survival_rows = []
            for item in survival_predictions[:10]:
                survival_rows.append(
                    [
                        _stringify_value(item.get("business_id")),
                        _format_probability(item.get("survival_probability")),
                        _clean_risk_label(item.get("risk_level")),
                        _format_datetime(item.get("created_at")),
                    ]
                )
            story.extend(
                [
                    _section_heading("Recent Survival Predictions", section_style),
                    _build_prediction_table(
                        ["Business ID", "Survival", "Risk Level", "Created"],
                        survival_rows,
                    ),
                    Spacer(1, 14),
                ]
            )

        if growth_forecasts:
            # Mirror the survival table style for projected-profit and growth outputs.
            growth_rows = []
            for item in growth_forecasts[:10]:
                growth_rows.append(
                    [
                        _stringify_value(item.get("business_id")),
                        _format_currency(item.get("predicted_profit_cfa")),
                        _stringify_value(item.get("growth_rate")),
                        _format_datetime(item.get("created_at")),
                    ]
                )
            story.extend(
                [
                    _section_heading("Recent Growth Forecasts", section_style),
                    _build_prediction_table(
                        ["Business ID", "Projected Profit", "Growth Rate", "Created"],
                        growth_rows,
                    ),
                    Spacer(1, 14),
                ]
            )

        executive_summary = latest_growth_report.get("executive_summary")
        prediction_explanation = latest_growth_report.get("prediction_explanation")
        optimal_business_model = latest_growth_report.get("optimal_business_model")
        tax_breakdown = latest_growth_report.get("cameroon_tax_breakdown")
        future_recommendations = _normalise_bullet_items(latest_growth_report.get("future_recommendations"))
        mit_plan = latest_growth_report.get("mit_business_plan")
        mit_plan = mit_plan if isinstance(mit_plan, dict) else {}

        if executive_summary:
            story.extend(
                [
                    _section_heading("Executive Summary", section_style),
                    Paragraph(_rich_text(executive_summary), body_style),
                    Spacer(1, 12),
                ]
            )

        if prediction_explanation:
            story.extend(
                [
                    _section_heading("Prediction Explanation", section_style),
                    Paragraph(_rich_text(prediction_explanation), body_style),
                    Spacer(1, 12),
                ]
            )

        if optimal_business_model:
            story.extend(
                [
                    _section_heading("Business Model Recommendation", section_style),
                    Paragraph(_rich_text(optimal_business_model), body_style),
                    Spacer(1, 12),
                ]
            )

        if future_recommendations:
            story.append(_section_heading("Priority Recommendations", section_style))
            for item in future_recommendations:
                story.append(Paragraph(_rich_text(item), bullet_style, bulletText="•"))
            story.append(Spacer(1, 12))

        if mit_plan:
            story.append(_section_heading("Business Plan Highlights", section_style))
            for label, key in [
                ("Market Analysis", "market_analysis"),
                ("Company Description", "company_description"),
                ("Service Product Line", "service_product_line"),
                ("Financial Projections", "financial_projections"),
            ]:
                if mit_plan.get(key):
                    story.append(Paragraph(label, styles["Heading3"]))
                    story.append(Paragraph(_rich_text(mit_plan.get(key)), body_style))
                    story.append(Spacer(1, 8))

        if tax_breakdown:
            story.extend(
                [
                    _section_heading("Tax Breakdown", section_style),
                    Paragraph(_rich_text(tax_breakdown), body_style),
                ]
            )

    doc.build(story, onFirstPage=_draw_page_footer, onLaterPages=_draw_page_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

@router.put("/preferences")
def update_preferences(prefs: PreferencesUpdate, current_user: dict = Depends(get_current_user)):
    """Saves the user's toggle states to the new JSONB column"""
    try:
        current_res = supabase.table("sme").select("preferences").eq("sme_id", current_user["sme_id"]).execute()
        current_prefs = current_res.data[0].get("preferences") if current_res.data else {}
        current_prefs = current_prefs if isinstance(current_prefs, dict) else {}
        combined_prefs = {**current_prefs, "notifs": prefs.notifs, "privacy": prefs.privacy}
        supabase.table("sme").update({"preferences": combined_prefs}).eq("sme_id", current_user["sme_id"]).execute()
        return {"status": "Success", "message": "Settings saved!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push-token")
def register_push_token(payload: PushTokenRegistration, current_user: dict = Depends(get_current_user)):
    try:
        current_res = supabase.table("sme").select("preferences").eq("sme_id", current_user["sme_id"]).execute()
        current_prefs = current_res.data[0].get("preferences") if current_res.data else {}
        next_prefs = merge_push_token(current_prefs, token=payload.token, platform=payload.platform)
        supabase.table("sme").update({"preferences": next_prefs}).eq("sme_id", current_user["sme_id"]).execute()
        return {"status": "Success", "message": "Push token registered."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/push-token")
def unregister_push_token(payload: PushTokenRemoval, current_user: dict = Depends(get_current_user)):
    try:
        current_res = supabase.table("sme").select("preferences").eq("sme_id", current_user["sme_id"]).execute()
        current_prefs = current_res.data[0].get("preferences") if current_res.data else {}
        next_prefs = remove_push_token(current_prefs, token=payload.token)
        supabase.table("sme").update({"preferences": next_prefs}).eq("sme_id", current_user["sme_id"]).execute()
        return {"status": "Success", "message": "Push token removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
def export_user_data(type: str = "all", format: str = "pdf", current_user: dict = Depends(get_current_user)):
    """Exports account data as a downloadable file."""
    try:
        sme_id = current_user["sme_id"]
        export_data = {"user": current_user}

        if type in ["all", "predictions"]:
            # Fetch related owner, business, and predictions
            owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
            if owner_res.data:
                owner_id = owner_res.data[0]["owner_id"]
                biz_res = supabase.table("business").select("*").eq("owner_id", owner_id).execute()
                if biz_res.data:
                    businesses = []
                    biz_ids = []
                    for item in biz_res.data:
                        biz_id = item["business_id"]
                        biz_ids.append(biz_id)
                        profile_res = supabase.table("business_profile").select("*").eq("business_id", biz_id).execute()
                        profile = profile_res.data[0] if profile_res.data else {}
                        businesses.append({**item, **profile})

                    export_data["businesses"] = businesses
                    surv_res = supabase.table("survival_prediction").select("*").in_("business_id", biz_ids).execute()
                    growth_res = supabase.table("growth_forecast").select("*").in_("business_id", biz_ids).execute()
                    export_data["survival_predictions"] = surv_res.data
                    export_data["growth_forecasts"] = growth_res.data

        export_format = format.lower()
        if export_format == "json":
            file_bytes = json.dumps(export_data, indent=4).encode("utf-8")
            media_type = "application/json"
            filename = f"BizNess_Export_{type}.json"
        else:
            file_bytes = _build_pdf_export(export_data, type)
            media_type = "application/pdf"
            filename = f"BizNess_Export_{type}.pdf"

        return StreamingResponse(
            BytesIO(file_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{action}")
def handle_danger_zone(action: str, current_user: dict = Depends(get_current_user)):
    """Handles History Deletion, Profile Resets, and Full Account Deletion"""
    sme_id = current_user["sme_id"]
    try:
        # Find the business ID first
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        owner_id = owner_res.data[0]["owner_id"] if owner_res.data else None
        
        if action == "history" and owner_id:
            biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).execute()
            if biz_res.data:
                for item in biz_res.data:
                    biz_id = item["business_id"]
                    supabase.table("survival_prediction").delete().eq("business_id", biz_id).execute()
                    supabase.table("growth_forecast").delete().eq("business_id", biz_id).execute()
                
        elif action == "profiles" and owner_id:
            # Because of ON DELETE CASCADE in your SQL, deleting the owner deletes the business and profiles!
            supabase.table("owner").delete().eq("sme_id", sme_id).execute()
            
        elif action == "account":
            # Deletes the actual user account (Everything else cascades)
            supabase.table("sme").delete().eq("sme_id", sme_id).execute()
            
        return {"status": "Success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
