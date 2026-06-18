"""Online market intelligence ingestion for BizSense.

The frontend should not call external news/funding sites directly. This service
fetches trusted feeds on the backend, normalizes the records, and stores them in
Supabase so the UI can display cited, cached information quickly.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from app.database import supabase

DEFAULT_FETCH_LIMIT = 20
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "BizSenseMarketIntelligence/1.0 (+https://bizness-frontend-cyan.vercel.app)"

# Default source definitions are intentionally small. Add more sources through
# the source_registry table when you have verified that their feeds are stable.
DEFAULT_SOURCES = [
    {
        "source_name": "Business in Cameroon",
        "source_url": "https://www.businessincameroon.com/index.php/component/obrss/fullrss",
        "source_type": "rss",
        "category": "business_news",
        "country": "Cameroon",
        "is_active": True,
    },
    {
        "source_name": "Disrupt Africa",
        "source_url": "https://disruptafrica.com/feed/",
        "source_type": "rss",
        "category": "startup_news",
        "country": "Africa",
        "is_active": True,
    },
]

CATEGORY_KEYWORDS = {
    "funding": ["grant", "fund", "funding", "investment", "accelerator", "call for applications", "entrepreneurship"],
    "policy": ["tax", "policy", "ministry", "regulation", "law", "government", "customs"],
    "market": ["market", "sector", "growth", "trade", "exports", "prices", "demand"],
    "startup_news": ["startup", "fintech", "tech", "digital", "innovation"],
}

INDUSTRY_KEYWORDS = {
    "Agriculture": ["agriculture", "agri", "farmer", "crop", "cocoa", "coffee", "poultry", "livestock"],
    "Retail": ["retail", "commerce", "shop", "consumer", "sales", "marketplace"],
    "Tech": ["tech", "digital", "software", "startup", "fintech", "mobile", "ai"],
    "Manufacturing": ["manufacturing", "factory", "production", "industrial", "processing"],
    "Food & Beverage": ["food", "restaurant", "beverage", "agro-processing", "catering"],
    "Transport": ["transport", "logistics", "mobility", "delivery", "shipping"],
    "Healthcare": ["health", "medical", "clinic", "pharma"],
    "Education": ["education", "school", "training", "learning", "students"],
    "Construction": ["construction", "housing", "real estate", "building"],
}

REGION_KEYWORDS = {
    "Douala": ["douala", "littoral"],
    "Yaounde": ["yaounde", "centre"],
    "Buea": ["buea", "south west", "southwest"],
    "Bamenda": ["bamenda", "north west", "northwest"],
    "Bafoussam": ["bafoussam", "west region"],
    "Garoua": ["garoua", "north region"],
}


@dataclass(frozen=True)
class IntelligenceSource:
    """A trusted feed or page that can be fetched by the ingestion job."""

    source_name: str
    source_url: str
    source_type: str
    category: str
    country: str = "Cameroon"
    is_active: bool = True


class IntelligenceFetchError(Exception):
    """Raised when a source cannot be fetched or parsed."""


def _strip_html(value: str | None) -> str:
    """Remove simple HTML tags from RSS descriptions."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> str | None:
    """Convert RSS/Atom date strings to ISO-8601 when possible."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _record_hash(source_url: str, title: str, url: str) -> str:
    """Create a stable duplicate key for a fetched item."""
    raw_key = f"{source_url}|{title.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _infer_category(default_category: str, title: str, summary: str) -> str:
    """Infer a more useful category from source text while keeping source default."""
    haystack = f"{title} {summary}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return default_category


def _infer_industries(title: str, summary: str) -> list[str]:
    """Tag an item with likely business industries based on keywords."""
    haystack = f"{title} {summary}".lower()
    matches = [industry for industry, keywords in INDUSTRY_KEYWORDS.items() if any(keyword in haystack for keyword in keywords)]
    return matches or ["General"]


def _infer_regions(title: str, summary: str) -> list[str]:
    """Tag an item with likely Cameroon regions/cities based on keywords."""
    haystack = f"{title} {summary}".lower()
    matches = [region for region, keywords in REGION_KEYWORDS.items() if any(keyword in haystack for keyword in keywords)]
    return matches or ["Cameroon"]


def _first_text(element: ET.Element, paths: list[str], namespaces: dict[str, str]) -> str:
    """Return the first non-empty child text from multiple RSS/Atom paths."""
    for path in paths:
        child = element.find(path, namespaces)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _parse_feed_items(xml_text: str, source: IntelligenceSource, limit: int) -> list[dict[str, Any]]:
    """Parse RSS or Atom XML into normalized intelligence records."""
    namespaces = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)

    rss_items = root.findall(".//item")
    atom_items = root.findall(".//atom:entry", namespaces)
    feed_items = rss_items or atom_items

    normalized_items: list[dict[str, Any]] = []
    for item in feed_items[:limit]:
        title = _first_text(item, ["title", "atom:title"], namespaces)
        summary = _strip_html(_first_text(item, ["description", "summary", "atom:summary", "content", "atom:content"], namespaces))
        published_at = _parse_date(_first_text(item, ["pubDate", "published", "atom:published", "updated", "atom:updated"], namespaces))

        link = _first_text(item, ["link"], namespaces)
        if not link:
            atom_link = item.find("atom:link", namespaces)
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""

        if not title or not link:
            continue

        category = _infer_category(source.category, title, summary)
        industries = _infer_industries(title, summary)
        regions = _infer_regions(title, summary)

        normalized_items.append(
            {
                "external_id": _record_hash(source.source_url, title, link),
                "title": title[:300],
                "summary": summary[:1200],
                "source_name": source.source_name,
                "source_url": source.source_url,
                "original_url": link,
                "category": category,
                "industries": industries,
                "regions": regions,
                "country": source.country,
                "published_at": published_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "credibility_score": 0.8,
                "raw_payload": {"source_type": source.source_type},
            }
        )

    return normalized_items


def _fetch_source(source: IntelligenceSource, limit: int = DEFAULT_FETCH_LIMIT) -> list[dict[str, Any]]:
    """Fetch one source and return normalized records."""
    if source.source_type not in {"rss", "atom"}:
        raise IntelligenceFetchError(f"Unsupported source type: {source.source_type}")

    response = requests.get(
        source.source_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _parse_feed_items(response.text, source, limit)


def get_active_sources() -> list[IntelligenceSource]:
    """Load active sources from Supabase, falling back to curated defaults."""
    try:
        response = supabase.table("source_registry").select("*").eq("is_active", True).execute()
        if response.data:
            return [
                IntelligenceSource(
                    source_name=row.get("source_name", "Unknown Source"),
                    source_url=row.get("source_url", ""),
                    source_type=row.get("source_type", "rss"),
                    category=row.get("category", "market"),
                    country=row.get("country", "Cameroon"),
                    is_active=bool(row.get("is_active", True)),
                )
                for row in response.data
                if row.get("source_url")
            ]
    except Exception as error:
        print(f"Source registry unavailable, using defaults: {error}")

    return [IntelligenceSource(**source) for source in DEFAULT_SOURCES]


def store_intelligence_items(items: list[dict[str, Any]]) -> int:
    """Insert new intelligence records and ignore duplicates by external_id."""
    inserted_count = 0
    for item in items:
        try:
            existing = supabase.table("market_intelligence_items").select("id").eq("external_id", item["external_id"]).limit(1).execute()
            if existing.data:
                continue
            supabase.table("market_intelligence_items").insert(item).execute()
            inserted_count += 1
        except Exception as error:
            print(f"Failed to store intelligence item '{item.get('title')}': {error}")
    return inserted_count


def refresh_market_intelligence(limit_per_source: int = DEFAULT_FETCH_LIMIT) -> dict[str, Any]:
    """Fetch all active sources, store new records, and return a refresh summary."""
    sources = get_active_sources()
    summary = {
        "sources_checked": len(sources),
        "items_fetched": 0,
        "items_inserted": 0,
        "errors": [],
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }

    for source in sources:
        try:
            items = _fetch_source(source, limit=limit_per_source)
            summary["items_fetched"] += len(items)
            summary["items_inserted"] += store_intelligence_items(items)
        except Exception as error:
            message = f"{source.source_name}: {error}"
            print(f"Market intelligence refresh error: {message}")
            summary["errors"].append(message)

    return summary


def list_intelligence_items(
    *,
    category: str | None = None,
    industry: str | None = None,
    region: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Read cached intelligence records for frontend display."""
    query = supabase.table("market_intelligence_items").select("*").order("published_at", desc=True).limit(limit)

    if category:
        query = query.eq("category", category)
    if industry:
        query = query.contains("industries", [industry])
    if region:
        query = query.contains("regions", [region])

    response = query.execute()
    return response.data or []
