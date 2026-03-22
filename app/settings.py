

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from app.database import supabase
from app.routers.dashboard import get_current_user # Reusing our secure bouncer!
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

class PreferencesUpdate(BaseModel):
    notifs: dict
    privacy: dict

@router.put("/preferences")
def update_preferences(prefs: PreferencesUpdate, current_user: dict = Depends(get_current_user)):
    """Saves the user's toggle states to the new JSONB column"""
    try:
        combined_prefs = {"notifs": prefs.notifs, "privacy": prefs.privacy}
        supabase.table("sme").update({"preferences": combined_prefs}).eq("sme_id", current_user["sme_id"]).execute()
        return {"status": "Success", "message": "Settings saved!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
def export_user_data(type: str = "all", current_user: dict = Depends(get_current_user)):
    """Exports data as a downloadable JSON file"""
    try:
        sme_id = current_user["sme_id"]
        export_data = {"user": current_user}

        if type in ["all", "predictions"]:
            # Fetch related owner, business, and predictions
            owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
            if owner_res.data:
                owner_id = owner_res.data[0]["owner_id"]
                biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).execute()
                if biz_res.data:
                    biz_id = biz_res.data[0]["business_id"]
                    surv_res = supabase.table("survival_prediction").select("*").eq("business_id", biz_id).execute()
                    growth_res = supabase.table("growth_forecast").select("*").eq("business_id", biz_id).execute()
                    export_data["survival_predictions"] = surv_res.data
                    export_data["growth_forecasts"] = growth_res.data

        # Convert to a downloadable file
        file_bytes = json.dumps(export_data, indent=4).encode('utf-8')
        return StreamingResponse(BytesIO(file_bytes), media_type="application/json", headers={"Content-Disposition": f"attachment; filename=BizSense_Export_{type}.json"})
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
                biz_id = biz_res.data[0]["business_id"]
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