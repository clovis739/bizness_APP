import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.database import supabase
from app.security import get_current_user

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)

# Store uploaded profile assets locally without introducing new database columns.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_ROOT = PROJECT_ROOT / "uploads" / "profile-assets"
AVATARS_DIR = UPLOADS_ROOT / "avatars"
LOGOS_DIR = UPLOADS_ROOT / "logos"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)
LOGOS_DIR.mkdir(parents=True, exist_ok=True)


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    business_name: Optional[str] = None
    industry: Optional[str] = None


# Resolve a deterministic static asset URL by looking up the saved file for an entity.
def _resolve_asset_url(request: Request, folder: Path, entity_id: str) -> str | None:
    matches = sorted(folder.glob(f"{entity_id}.*"))
    if not matches:
        return None

    base_url = str(request.base_url).rstrip("/")
    relative_path = matches[0].relative_to(PROJECT_ROOT / "uploads").as_posix()
    return f"{base_url}/uploads/{relative_path}"


# Save the uploaded image under a stable filename so later reads do not need a database field.
def _save_asset(file: UploadFile, folder: Path, entity_id: str) -> str:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported.")

    suffix = Path(file.filename or "").suffix or mimetypes.guess_extension(file.content_type) or ".jpg"
    target_path = folder / f"{entity_id}{suffix.lower()}"

    for existing_file in folder.glob(f"{entity_id}.*"):
        if existing_file != target_path and existing_file.exists():
            existing_file.unlink()

    file.file.seek(0)
    target_path.write_bytes(file.file.read())
    return target_path.name


# Follow the SME -> Owner -> Business relationship once so the endpoints stay consistent.
def _get_owner_and_business(sme_id: str):
    owner_res = supabase.table("owner").select("*").eq("sme_id", sme_id).execute()
    owner = owner_res.data[0] if owner_res.data else None
    if not owner:
        return None, None

    business_res = supabase.table("business").select("*").eq("owner_id", owner["owner_id"]).execute()
    business = business_res.data[0] if business_res.data else None
    return owner, business


@router.get("/me")
def get_dashboard_data(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Fetch the signed-in user's current business context and recent predictions.
    """
    try:
        sme_id = current_user["sme_id"]
        owner, business_data = _get_owner_and_business(sme_id)

        user_payload = {
            "name": current_user["name"],
            "email": current_user["email"],
            "sme_id": sme_id,
            "preferences": current_user.get("preferences", {}),
            "avatar_url": _resolve_asset_url(request, AVATARS_DIR, sme_id),
        }

        if not owner:
            return {
                "status": "Success",
                "data": {
                    "user": user_payload,
                    "has_business_profile": False,
                    "business": None,
                    "businesses": [],
                    "survival_history": [],
                    "growth_history": [],
                }
            }

        business_payload = None
        businesses_payload = []
        survival_history = []
        growth_history = []

        if business_data:
            profile_res = (
                supabase
                .table("business_profile")
                .select("*")
                .eq("business_id", business_data["business_id"])
                .execute()
            )
            profile_data = profile_res.data[0] if profile_res.data else None
            business_payload = {**business_data, **profile_data} if profile_data else business_data
            business_payload["phone"] = owner.get("phone")
            business_payload["logo_url"] = _resolve_asset_url(request, LOGOS_DIR, business_data["business_id"])
            businesses_payload = [business_payload]

            survival_history = (
                supabase
                .table("survival_prediction")
                .select("*")
                .eq("business_id", business_data["business_id"])
                .order("created_at", desc=True)
                .limit(5)
                .execute()
                .data
            )

            growth_history = (
                supabase
                .table("growth_forecast")
                .select("forecast_id, predicted_profit_cfa, growth_rate, full_report, chart_data, created_at")
                .eq("business_id", business_data["business_id"])
                .order("created_at", desc=True)
                .limit(5)
                .execute()
                .data
            )

        return {
            "status": "Success",
            "data": {
                "user": user_payload,
                "has_business_profile": business_payload is not None,
                "business": business_payload,
                "businesses": businesses_payload,
                "survival_history": survival_history,
                "growth_history": growth_history,
            }
        }
    except Exception as error:
        print(f"DASHBOARD ERROR: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard data.") from error


@router.put("/update-profile")
def update_user_profile(payload: ProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """
    Persist the exact profile fields supported by the backend.
    """
    try:
        sme_id = current_user["sme_id"]
        full_name = f"{payload.first_name or ''} {payload.last_name or ''}".strip()

        if full_name:
            supabase.table("sme").update({"name": full_name}).eq("sme_id", sme_id).execute()

        owner, business_data = _get_owner_and_business(sme_id)
        if owner:
            owner_update = {}
            if full_name:
                owner_update["full_name"] = full_name
            if payload.phone is not None:
                owner_update["phone"] = payload.phone

            if owner_update:
                supabase.table("owner").update(owner_update).eq("owner_id", owner["owner_id"]).execute()

            business_update = {}
            if payload.business_name:
                business_update["name"] = payload.business_name
            if payload.industry:
                business_update["industry"] = payload.industry

            if business_update and business_data:
                supabase.table("business").update(business_update).eq("business_id", business_data["business_id"]).execute()

        return {"status": "Success", "message": "Profile updated successfully!"}
    except Exception as error:
        print(f"PROFILE UPDATE ERROR: {error}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(error)}") from error


@router.post("/upload-avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """
    Upload or replace the signed-in user's avatar image.
    """
    try:
        _save_asset(file, AVATARS_DIR, current_user["sme_id"])
        return {
            "status": "Success",
            "message": "Profile photo uploaded successfully!",
            "url": _resolve_asset_url(request, AVATARS_DIR, current_user["sme_id"]),
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail="Failed to upload profile photo.") from error


@router.post("/upload-business-logo")
async def upload_business_logo(request: Request, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """
    Upload or replace the current business logo for the signed-in SME.
    """
    try:
        _, business_data = _get_owner_and_business(current_user["sme_id"])
        if not business_data:
            raise HTTPException(status_code=404, detail="Business profile not found.")

        _save_asset(file, LOGOS_DIR, business_data["business_id"])
        return {
            "status": "Success",
            "message": "Business logo uploaded successfully!",
            "url": _resolve_asset_url(request, LOGOS_DIR, business_data["business_id"]),
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail="Failed to upload business logo.") from error
