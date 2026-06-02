import json
import re
from datetime import datetime
from html import escape
from io import BytesIO
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from app.database import supabase
from app.routers.dashboard import get_current_user
from app.routers.communication import send_html_email
from app.services.push_notifications import extract_push_token_values, send_expo_push_notifications
from app.services.forecast_math import calculate_growth_rate
from app.limiter import limiter
from app.redis_client import redis_db
from app_v2.schemas_v2 import PredictionRequestV2
from app_v2.services.ml_service_v2 import run_predictions
from app_v2.services.llm_service_v2 import generate_business_report, extract_ml_features_from_pdf

import os

# ============================================================
# BizSense OS — Predict Router V2
# Uses V3 models + Groq. Reads from business_profile_v2.
# Cache key uses _v2 suffix to avoid V1 cache collisions.
# ============================================================

router = APIRouter(
    prefix="/api/v2/predict",
    tags=["AI Predictions V2"]
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-vercel-app-url.vercel.app")
BIZNESS_PRIMARY = colors.HexColor("#476DDC")
BIZNESS_PRIMARY_DARK = colors.HexColor("#020842")
BIZNESS_TEXT = colors.HexColor("#3E3B3B")
BIZNESS_MUTED = colors.HexColor("#64748B")
BIZNESS_SURFACE = colors.HexColor("#EFF6FF")
BIZNESS_PAGE = colors.HexColor("#E3F0FF")
BIZNESS_BORDER = colors.HexColor("#D7E3F7")
BIZNESS_SUCCESS = colors.HexColor("#059669")


def _user_language_from_preferences(prefs):
    appearance = prefs.get("appearance", {}) if isinstance(prefs, dict) else {}
    language = str(appearance.get("language") or "en").lower()
    return "fr" if language.startswith("fr") else "en"


def _pdf_label(label, language):
    if language != "fr":
        return label
    labels = {
        "BizSense OS": "BizSense OS",
        "AI Advisory Report": "Rapport consultatif IA",
        "Prepared for": "Prepare pour",
        "Survival Probability": "Probabilite de survie",
        "Projected Profit": "Benefice projete",
        "Risk Level": "Niveau de risque",
        "Executive Summary": "Resume executif",
        "Prediction Explanation": "Explication de la prediction",
        "Optimal Business Model": "Modele economique recommande",
        "Cameroon Tax Breakdown": "Fiscalite camerounaise",
        "Market Intelligence": "Intelligence marche",
        "Sector Trends": "Tendances du secteur",
        "Growth Opportunities": "Opportunites de croissance",
        "Risk Watchlist": "Risques a surveiller",
        "90-Day Growth Plan": "Plan de croissance sur 90 jours",
        "KPIs to Track": "KPI a suivre",
        "Future Recommendations": "Recommandations futures",
        "SWOT Analysis": "Analyse SWOT",
        "Regional Competitor Intelligence": "Intelligence concurrentielle regionale",
        "Generated": "Genere",
    }
    return labels.get(label, label)


def _report_text(value):
    if value is None:
        return "Not available."
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    text = str(value).strip()
    return text or "Not available."


def _rich_pdf_text(value):
    source = escape(_report_text(value))
    source = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", source)
    source = source.replace("\n", "<br/>")
    return source


def _normalise_items(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _report_text(value)
    lines = [line.strip(" -*\t") for line in text.splitlines()]
    return [line for line in lines if line]


def _build_report_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BizReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            alignment=TA_CENTER,
            textColor=BIZNESS_PRIMARY_DARK,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "BizReportSubtitle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=BIZNESS_MUTED,
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "BizReportSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=BIZNESS_PRIMARY_DARK,
            spaceBefore=6,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "BizReportBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=16,
            textColor=BIZNESS_TEXT,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "BizReportBullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.2,
            leading=15,
            leftIndent=16,
            bulletIndent=4,
            textColor=BIZNESS_TEXT,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "BizReportSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=BIZNESS_MUTED,
        ),
    }


def _section_card(title, content, report_styles):
    table = Table(
        [[Paragraph(title, report_styles["section"])], [Paragraph(_rich_pdf_text(content), report_styles["body"])]],
        colWidths=[500],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
        ("LINEBELOW", (0, 0), (0, 0), 0.75, BIZNESS_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table



def _append_numbered_items(story, title, items, report_styles):
    items = _normalise_items(items)
    if not items:
        return
    story.append(Paragraph(_pdf_label(title, report_styles.get("language", "en")), report_styles["section"]))
    rows = [[Paragraph(f"<b>{index}</b>", report_styles["body"]), Paragraph(_rich_pdf_text(item), report_styles["body"])] for index, item in enumerate(items, start=1)]
    table = Table(rows, colWidths=[28, 472], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 12)])


def _append_market_intelligence_sections(story, report_data, report_styles):
    language = report_data.get("report_language", "en")
    report_styles["language"] = language
    market = report_data.get("market_intelligence") if isinstance(report_data.get("market_intelligence"), dict) else {}
    if market:
        market_text = []
        if market.get("sector_snapshot"):
            market_text.append(f"**Sector snapshot:** {market.get('sector_snapshot')}")
        if market.get("competition_pressure"):
            market_text.append(f"**Competition pressure:** {market.get('competition_pressure')}")
        if market.get("local_demand_signals"):
            signals = "\n".join(f"- {item}" for item in _normalise_items(market.get("local_demand_signals")))
            market_text.append(f"**Local demand signals:**\n{signals}")
        if market.get("customer_behavior_trends"):
            trends = "\n".join(f"- {item}" for item in _normalise_items(market.get("customer_behavior_trends")))
            market_text.append(f"**Customer behavior trends:**\n{trends}")
        story.append(_section_card(_pdf_label("Market Intelligence", language), "\n\n".join(market_text), report_styles))
        story.append(Spacer(1, 12))

    _append_numbered_items(story, _pdf_label("Sector Trends", language), report_data.get("sector_trends", []), report_styles)

    opportunities = report_data.get("growth_opportunities") if isinstance(report_data.get("growth_opportunities"), list) else []
    if opportunities:
        story.append(Paragraph(_pdf_label("Growth Opportunities", language), report_styles["section"]))
        rows = [[Paragraph("Opportunity", report_styles["body"]), Paragraph("Why It Matters / How To Act", report_styles["body"]), Paragraph("Difficulty", report_styles["body"])]]
        for item in opportunities:
            if not isinstance(item, dict):
                continue
            rows.append([
                Paragraph(_rich_pdf_text(item.get("title", "Opportunity")), report_styles["body"]),
                Paragraph(_rich_pdf_text(f"{item.get('why_it_matters', '')}\n{item.get('how_to_act', '')}"), report_styles["body"]),
                Paragraph(_rich_pdf_text(item.get("difficulty", "Medium")), report_styles["body"]),
            ])
        table = Table(rows, colWidths=[130, 285, 85], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 12)])

    risks = report_data.get("risk_watchlist") if isinstance(report_data.get("risk_watchlist"), list) else []
    if risks:
        story.append(Paragraph(_pdf_label("Risk Watchlist", language), report_styles["section"]))
        rows = [[Paragraph("Risk", report_styles["body"]), Paragraph("Impact", report_styles["body"]), Paragraph("Mitigation", report_styles["body"])]]
        for item in risks:
            if not isinstance(item, dict):
                continue
            rows.append([
                Paragraph(_rich_pdf_text(item.get("risk", "Risk")), report_styles["body"]),
                Paragraph(_rich_pdf_text(item.get("impact", "")), report_styles["body"]),
                Paragraph(_rich_pdf_text(item.get("mitigation", "")), report_styles["body"]),
            ])
        table = Table(rows, colWidths=[140, 180, 180], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 12)])

    plan = report_data.get("next_90_day_action_plan") if isinstance(report_data.get("next_90_day_action_plan"), dict) else {}
    if plan:
        plan_text = []
        for label, key in [("Days 1-30", "days_1_30"), ("Days 31-60", "days_31_60"), ("Days 61-90", "days_61_90")]:
            items = _normalise_items(plan.get(key, []))
            if items:
                actions = "\n".join(f"- {item}" for item in items)
                plan_text.append(f"**{label}**\n{actions}")
        if plan_text:
            story.append(_section_card(_pdf_label("90-Day Growth Plan", language), "\n\n".join(plan_text), report_styles))
            story.append(Spacer(1, 12))

    kpis = report_data.get("recommended_kpis") if isinstance(report_data.get("recommended_kpis"), list) else []
    if kpis:
        story.append(Paragraph(_pdf_label("KPIs to Track", language), report_styles["section"]))
        rows = [[Paragraph("KPI", report_styles["body"]), Paragraph("Target", report_styles["body"]), Paragraph("Why It Matters", report_styles["body"])]]
        for item in kpis:
            if not isinstance(item, dict):
                continue
            rows.append([
                Paragraph(_rich_pdf_text(item.get("name", "KPI")), report_styles["body"]),
                Paragraph(_rich_pdf_text(item.get("target", "")), report_styles["body"]),
                Paragraph(_rich_pdf_text(item.get("why_it_matters", "")), report_styles["body"]),
            ])
        table = Table(rows, colWidths=[135, 150, 215], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 12)])


def _append_swot_sections(story, report_data, report_styles):
    language = report_data.get("report_language", "en")
    swot = report_data.get("swot_analysis") if isinstance(report_data.get("swot_analysis"), dict) else {}
    if not swot:
        return
    story.append(Paragraph(_pdf_label("SWOT Analysis", language), report_styles["section"]))
    rows = []
    for left_key, right_key in [("strengths", "weaknesses"), ("opportunities", "threats")]:
        left_title = left_key.replace("_", " ").title()
        right_title = right_key.replace("_", " ").title()
        left_items = "\n".join(f"- {item}" for item in _normalise_items(swot.get(left_key, []))) or "Not available."
        right_items = "\n".join(f"- {item}" for item in _normalise_items(swot.get(right_key, []))) or "Not available."
        rows.append([
            Paragraph(f"<b>{left_title}</b><br/>{_rich_pdf_text(left_items)}", report_styles["body"]),
            Paragraph(f"<b>{right_title}</b><br/>{_rich_pdf_text(right_items)}", report_styles["body"]),
        ])
    table = Table(rows, colWidths=[250, 250], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 12)])


def _append_regional_competitor_sections(story, report_data, report_styles):
    language = report_data.get("report_language", "en")
    competitors = report_data.get("regional_competitors") if isinstance(report_data.get("regional_competitors"), dict) else {}
    if not competitors:
        return
    story.append(Paragraph(_pdf_label("Regional Competitor Intelligence", language), report_styles["section"]))
    for title, key in [("Local Competitors", "local"), ("National Competitors", "national"), ("International Competitors", "international")]:
        entries = competitors.get(key, [])
        if not entries:
            continue
        story.append(Paragraph(title, report_styles["body"]))
        rows = [[
            Paragraph("Name", report_styles["body"]),
            Paragraph("Type", report_styles["body"]),
            Paragraph("Threat", report_styles["body"]),
            Paragraph("Why They Matter", report_styles["body"]),
        ]]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            rows.append([
                Paragraph(_rich_pdf_text(entry.get("name", "Competitor")), report_styles["body"]),
                Paragraph(_rich_pdf_text(entry.get("type", "Direct")), report_styles["body"]),
                Paragraph(_rich_pdf_text(entry.get("threat_level", "")), report_styles["body"]),
                Paragraph(_rich_pdf_text(entry.get("why_they_matter", "")), report_styles["body"]),
            ])
        table = Table(rows, colWidths=[102, 58, 48, 292], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BIZNESS_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 10)])

def _draw_report_footer(canvas, doc):
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(BIZNESS_BORDER)
    canvas.line(doc.leftMargin, 38, width - doc.rightMargin, 38)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BIZNESS_MUTED)
    canvas.drawString(doc.leftMargin, 24, "BizSense OS - AI Advisory Report")
    canvas.drawRightString(width - doc.rightMargin, 24, f"Page {doc.page}")
    canvas.restoreState()


@router.post("/generate")
@limiter.limit("3/minute")
def generate_prediction_v2(
    request: Request,
    payload: PredictionRequestV2,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Core V2 prediction endpoint.
    1. Checks Redis cache (v2 key)
    2. Fetches real data from business_profile_v2 (all V3 fields)
    3. Runs V3 ML models (CatBoost calibrated + LightGBM + Cox PH)
    4. Calls Groq for advisory report
    5. Saves to survival_prediction + growth_forecast
    6. Caches for 24 hours
    7. Sends email + push notification (background)
    """
    try:
        sme_id = current_user["sme_id"]
        user_prefs_res = supabase.table("sme").select("preferences").eq("sme_id", sme_id).execute()
        prefs_data = (user_prefs_res.data[0].get("preferences") or {}) if user_prefs_res.data else {}
        report_language = _user_language_from_preferences(prefs_data)

        # Cache check is language-aware so French and English reports do not collide.
        cache_key = f"business_report_{payload.business_id}_{report_language}_v2"
        if redis_db:
            try:
                cached = redis_db.get(cache_key)
                if cached:
                    print(f"CACHE HIT ({report_language}): {payload.business_id}")
                    return json.loads(cached)
            except Exception as redis_err:
                print(f"Redis read failed, continuing without cache: {redis_err}")

        print(f"CACHE MISS ({report_language}). Generating report for: {payload.business_id}")

        # ── Security: verify ownership ───────────────────────────
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: No owner profile found.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id", "industry").eq("owner_id", owner_id).eq("business_id", payload.business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")
        industry = biz_res.data[0]["industry"]

        # ── Fetch V2 profile (all V3 fields) ────────────────────
        profile_res = supabase.table("business_profile_v2").select("*").eq("business_id", payload.business_id).execute()
        if not profile_res.data:
            raise HTTPException(
                status_code=404,
                detail="No V2 business profile found. Please register via POST /api/v2/business/register first."
            )
        profile = profile_res.data[0]

        # ── Build ML input from real stored data ─────────────────
        ml_input = {
            "region":                    profile["region"],
            "sector":                    profile["sector"],
            "industry":                  industry,
            "startup_capital_cfa":       profile["startup_capital_cfa"],
            "employees":                 profile["employees"],
            "years_of_experience":       profile["years_of_experience"],
            "year_started":              profile["year_started"],
            "transport_cost_percentage": profile["transport_cost_percentage"],
            "energy_cost_percentage":    profile["energy_cost_percentage"],
            # V3 new fields — real values, no hardcoding
            "has_business_plan":         profile.get("has_business_plan", False),
            "formal_financial_records":  profile.get("formal_financial_records", False),
            "registered_formal":         profile.get("registered_formal", False),
            "owner_education_level":     profile.get("owner_education_level", "Secondary"),
            "competition_level":         profile.get("competition_level", "Medium"),
            "access_to_financing":       profile.get("access_to_financing", "No"),
            "financing_method":          profile.get("financing_method", "Own Resources"),
            "owner_hours_per_week":      profile.get("owner_hours_per_week", 40),
            "business_type":             profile.get("business_type", "Sole Proprietorship"),
        }

        # ── Run V3 ML models ─────────────────────────────────────
        print(f"🧠 Running V3 ML Analysis for: {payload.business_id}")
        ai_results = run_predictions(ml_input)

        # ── Generate Groq advisory report ────────────────────────
        ai_payload = generate_business_report(ml_input, ai_results, language=report_language)

        # ── Save to database ─────────────────────────────────────
        supabase.table("survival_prediction").insert({
            "business_id":        payload.business_id,
            "survival_probability": ai_results["survival_probability"],
            "risk_level":         ai_results["risk_level"],
        }).execute()

        growth_rate = calculate_growth_rate(
            ai_results["projected_profit_cfa"],
            ml_input["startup_capital_cfa"],
        )

        supabase.table("growth_forecast").insert({
            "business_id":          payload.business_id,
            "predicted_profit_cfa": ai_results["projected_profit_cfa"],
            "growth_rate":          growth_rate,
            "chart_data":           ai_payload.get("chart_data", {}),
            "full_report":          ai_payload,
        }).execute()

        # ── Build final response ─────────────────────────────────
        # Remove internal feature context from public response
        public_results = {k: v for k, v in ai_results.items() if k != "_feature_context"}

        final_response = {
            "status":  "Success",
            "message": "V2 AI Analysis & Consulting Report Complete!",
            "api_version": "v2",
            "data": {
                "predictions":    public_results,
                "advisory_report": ai_payload,
            }
        }

        # ── Cache for 24 hours ───────────────────────────────────
        if redis_db:
            try:
                redis_db.setex(cache_key, 86400, json.dumps(final_response))
            except Exception as redis_err:
                print(f"⚠️ Redis write failed (report still returned): {redis_err}")

        # ── Background: email + push notifications ───────────────
        notifs = prefs_data.get("notifs", {})

        if notifs.get("prediction_complete", True):
            user_email = current_user["email"]
            user_name  = current_user.get("name", "Entrepreneur")
            survival_pct = round(ai_results["survival_probability"] * 100, 1)
            email_html = f"""
            <html>
                <body style="font-family:Arial,sans-serif;padding:20px;background:#f8f9fa;">
                    <div style="max-width:600px;margin:0 auto;background:#fff;padding:30px;border-radius:12px;border-top:5px solid #3B7FFF;">
                        <h2 style="color:#111827;">Your AI Prediction is Ready! 🚀</h2>
                        <p style="color:#4b5563;">Hello {user_name},</p>
                        <p style="color:#4b5563;">Your BizSense V3 AI analysis is complete.</p>
                        <p style="color:#4b5563;font-size:18px;font-weight:bold;">3-Year Survival Probability: {survival_pct}%</p>
                        <p style="color:#4b5563;">Risk Level: {ai_results['risk_level']}</p>
                        <a href="{FRONTEND_URL}/history"
                           style="display:inline-block;background:#3B7FFF;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:bold;margin-top:10px;">
                            View Full Report
                        </a>
                    </div>
                </body>
            </html>
            """
            background_tasks.add_task(
                send_html_email, user_email,
                "Your BizSense V2 AI Prediction is Ready!", email_html
            )

        if notifs.get("push_mobile", True):
            push_tokens = extract_push_token_values(prefs_data)
            if push_tokens:
                background_tasks.add_task(
                    send_expo_push_notifications,
                    push_tokens=push_tokens,
                    title="V2 Prediction complete",
                    body=f"Your BizSense V3 AI report is ready.",
                    data={"business_id": payload.business_id, "type": "prediction_complete_v2"},
                )

        return final_response

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 V2 PREDICTION CRASH: {str(e)}")
        raise HTTPException(status_code=500, detail=f"V2 Prediction Error: {str(e)}")


@router.get("/history/{business_id}")
def get_prediction_history_v2(
    business_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Returns full prediction history for a business. Shared table with V1."""
    try:
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        surv  = supabase.table("survival_prediction").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()
        growth = supabase.table("growth_forecast").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()

        return {
            "status": "Success",
            "data": {
                "business_id":    business_id,
                "survival_history": surv.data,
                "growth_history":   growth.data,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History Error: {str(e)}")


@router.post("/upload-pdf")
async def analyze_pdf_v2(
    business_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a PDF business plan. Groq extracts V3 features,
    V3 models run prediction.
    """
    try:
        sme_id = current_user["sme_id"]
        user_prefs_res = supabase.table("sme").select("preferences").eq("sme_id", sme_id).execute()
        prefs_data = (user_prefs_res.data[0].get("preferences") or {}) if user_prefs_res.data else {}
        report_language = _user_language_from_preferences(prefs_data)
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_res.data[0]["owner_id"]).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF documents are accepted.")

        MAX_FILE_SIZE = 5 * 1024 * 1024
        pdf_bytes = await file.read(MAX_FILE_SIZE + 1)
        if len(pdf_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds the 5MB limit.")

        ml_input = extract_ml_features_from_pdf(pdf_bytes)
        if "error" in ml_input:
            raise HTTPException(status_code=500, detail="Failed to extract data from PDF.")

        ai_results  = run_predictions(ml_input)
        ai_payload  = generate_business_report(ml_input, ai_results, language=report_language)
        public_results = {k: v for k, v in ai_results.items() if k != "_feature_context"}

        return {
            "status":          "Success",
            "message":         "PDF analyzed successfully with V3 models!",
            "extracted_data":  ml_input,
            "predictions":     public_results,
            "advisory_report": ai_payload,
            "api_version":     "v2"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Analysis Error: {str(e)}")


@router.get("/download-report/{business_id}")
def download_report_v2(
    business_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generates and streams the latest report as a branded PDF file."""
    try:
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = (
            supabase
            .table("business")
            .select("business_id, name, industry")
            .eq("owner_id", owner_id)
            .eq("business_id", business_id)
            .execute()
        )
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")
        business = biz_res.data[0]

        growth_res = (
            supabase
            .table("growth_forecast")
            .select("predicted_profit_cfa, growth_rate, full_report, created_at")
            .eq("business_id", business_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not growth_res.data or not growth_res.data[0].get("full_report"):
            raise HTTPException(status_code=404, detail="No report found. Generate a prediction first.")

        survival_res = (
            supabase
            .table("survival_prediction")
            .select("survival_probability, risk_level, created_at")
            .eq("business_id", business_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        latest_growth = growth_res.data[0]
        latest_survival = survival_res.data[0] if survival_res.data else {}
        report_data = latest_growth["full_report"]
        report_data = report_data if isinstance(report_data, dict) else {}
        report_language = report_data.get("report_language", "en")

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=48,
            leftMargin=48,
            topMargin=52,
            bottomMargin=54,
            title="BizSense AI Advisory Report",
            author="BizSense OS",
        )
        report_styles = _build_report_styles()
        story = []

        generated_at = datetime.now().strftime("%b %d, %Y %I:%M %p")
        business_name = business.get("name") or "Business Profile"
        industry = business.get("industry") or "Business"
        survival_probability = latest_survival.get("survival_probability")
        survival_text = "Not available"
        if survival_probability is not None:
            survival_text = f"{float(survival_probability) * 100:.1f}%"
        profit_value = latest_growth.get("predicted_profit_cfa")
        profit_text = f"{float(profit_value):,.0f} CFA" if profit_value is not None else "Not available"

        cover = Table(
            [
                [Paragraph("BizSense OS", report_styles["small"])],
                [Paragraph(_pdf_label("AI Advisory Report", report_language), report_styles["title"])],
                [Paragraph(f"{_pdf_label("Prepared for", report_language)} <b>{escape(str(business_name))}</b> - {escape(str(industry))}", report_styles["subtitle"])],
            ],
            colWidths=[500],
        )
        cover.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BIZNESS_SURFACE),
            ("BOX", (0, 0), (-1, -1), 1, BIZNESS_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 18),
            ("RIGHTPADDING", (0, 0), (-1, -1), 18),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.extend([cover, Spacer(1, 14)])

        metrics = Table(
            [[
                Paragraph(f"<b>{survival_text}</b><br/><font color='#64748B'>{_pdf_label('Survival Probability', report_language)}</font>", report_styles["body"]),
                Paragraph(f"<b>{profit_text}</b><br/><font color='#64748B'>{_pdf_label('Projected Profit', report_language)}</font>", report_styles["body"]),
                Paragraph(f"<b>{escape(str(latest_survival.get('risk_level') or 'Not available'))}</b><br/><font color='#64748B'>{_pdf_label('Risk Level', report_language)}</font>", report_styles["body"]),
            ]],
            colWidths=[160, 170, 170],
        )
        metrics.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BIZNESS_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.extend([metrics, Spacer(1, 14)])

        sections = [
            (_pdf_label("Executive Summary", report_language), report_data.get("executive_summary", "")),
            (_pdf_label("Prediction Explanation", report_language), report_data.get("prediction_explanation", "")),
            (_pdf_label("Optimal Business Model", report_language), report_data.get("optimal_business_model", "")),
            (_pdf_label("Cameroon Tax Breakdown", report_language), report_data.get("cameroon_tax_breakdown", "")),
        ]
        for title, section_text in sections:
            story.append(_section_card(title, section_text, report_styles))
            story.append(Spacer(1, 12))

        _append_market_intelligence_sections(story, report_data, report_styles)

        recommendations = _normalise_items(report_data.get("future_recommendations", []))
        if recommendations:
            story.append(Paragraph(_pdf_label("Future Recommendations", report_language), report_styles["section"]))
            rec_rows = []
            for index, rec in enumerate(recommendations, start=1):
                rec_rows.append([
                    Paragraph(f"<b>{index}</b>", report_styles["body"]),
                    Paragraph(_rich_pdf_text(rec), report_styles["body"]),
                ])
            rec_table = Table(rec_rows, colWidths=[28, 472], hAlign="LEFT")
            rec_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.75, BIZNESS_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BIZNESS_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.extend([rec_table, Spacer(1, 12)])

        _append_swot_sections(story, report_data, report_styles)
        _append_regional_competitor_sections(story, report_data, report_styles)

        story.append(Paragraph(f"{_pdf_label("Generated", report_language)} {generated_at}. This report is based on the latest saved prediction for this business.", report_styles["small"]))

        doc.build(story, onFirstPage=_draw_report_footer, onLaterPages=_draw_report_footer)
        buffer.seek(0)

        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(business_name)).strip("_") or "Business"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=BizSense_Report_{safe_name}.pdf"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Export Error: {str(e)}")
