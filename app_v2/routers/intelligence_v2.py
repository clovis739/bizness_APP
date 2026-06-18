"""Market intelligence routes for BizSense V2.

These endpoints expose cached, source-linked intelligence to the UI. External
fetching is handled by the service layer so frontend screens remain fast and
stable even when a third-party source is slow or unavailable.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import supabase
from app.routers.dashboard import get_current_user
from app_v2.schemas_v2 import IntelligenceRefreshRequest, IntelligenceSourceCreate
from app_v2.services.intelligence_fetcher import list_intelligence_items, refresh_market_intelligence

router = APIRouter(prefix="/api/v2/intelligence", tags=["Market Intelligence V2"])


@router.get("/items")
def get_intelligence_items(
    category: str | None = Query(default=None, description="Filter by category such as funding, policy, market, startup_news."),
    industry: str | None = Query(default=None, description="Filter by tagged industry, for example Retail or Agriculture."),
    region: str | None = Query(default=None, description="Filter by tagged region/city, for example Douala."),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Return cached source-linked intelligence items for UI cards/lists."""
    try:
        return {
            "status": "Success",
            "items": list_intelligence_items(category=category, industry=industry, region=region, limit=limit),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load intelligence items: {error}") from error


@router.get("/news")
def get_market_news(limit: int = Query(default=20, ge=1, le=100)):
    """Convenience endpoint for general market/startup news cards."""
    try:
        items = list_intelligence_items(category="startup_news", limit=limit)
        if len(items) < limit:
            items.extend(list_intelligence_items(category="business_news", limit=limit - len(items)))
        return {"status": "Success", "items": items[:limit]}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load market news: {error}") from error


@router.get("/funding")
def get_funding_opportunities(
    industry: str | None = Query(default=None),
    region: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return funding, grant, accelerator, and opportunity intelligence."""
    try:
        return {
            "status": "Success",
            "items": list_intelligence_items(category="funding", industry=industry, region=region, limit=limit),
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load funding opportunities: {error}") from error


@router.get("/policy-updates")
def get_policy_updates(limit: int = Query(default=20, ge=1, le=100)):
    """Return policy, tax, regulation, and government update intelligence."""
    try:
        return {"status": "Success", "items": list_intelligence_items(category="policy", limit=limit)}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load policy updates: {error}") from error


@router.get("/sources")
def get_sources(current_user: dict = Depends(get_current_user)):
    """List configured source feeds for admin/debugging use."""
    try:
        response = supabase.table("source_registry").select("*").order("created_at", desc=True).execute()
        return {"status": "Success", "sources": response.data or []}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load intelligence sources: {error}") from error


@router.post("/sources")
def create_source(source: IntelligenceSourceCreate, current_user: dict = Depends(get_current_user)):
    """Add a trusted RSS/Atom source without changing backend code."""
    try:
        payload = source.model_dump()
        response = supabase.table("source_registry").insert(payload).execute()
        return {"status": "Success", "source": response.data[0] if response.data else payload}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to create intelligence source: {error}") from error


@router.post("/refresh")
def refresh_intelligence(
    payload: IntelligenceRefreshRequest = IntelligenceRefreshRequest(),
    current_user: dict = Depends(get_current_user),
):
    """Fetch online sources now and store new deduplicated records."""
    try:
        return {"status": "Success", "summary": refresh_market_intelligence(payload.limit_per_source)}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to refresh market intelligence: {error}") from error