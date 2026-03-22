# app/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from app.database import supabase

# Initialize the Router
router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)

# ==========================================
# SCHEMA FOR PROFILE UPDATES
# ==========================================
class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    
    # Business data
    business_name: Optional[str] = None
    industry: Optional[str] = None


# ==========================================
# SECURITY DEPENDENCY
# ==========================================
def get_current_user(request: Request):
    """Checks for the secure cookie and fetches the SME user."""
    sme_id = request.cookies.get("bizness_session")
    
    if not sme_id:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
    
    res = supabase.table("sme").select("*").eq("sme_id", sme_id).execute()
    
    if len(res.data) == 0:
        raise HTTPException(status_code=401, detail="User session invalid or expired.")
        
    return res.data[0]


# ==========================================
# DASHBOARD DATA ENDPOINT
# ==========================================
@router.get("/me")
def get_dashboard_data(current_user: dict = Depends(get_current_user)):
    """
    Fetches the SME's profile, business details, and recent AI predictions.
    Traces the relational database chain: SME -> Owner -> Business -> Predictions
    """
    try:
        sme_id = current_user["sme_id"]
        
        # 1. Fetch Owner Record
        owner_res = supabase.table("owner").select("*").eq("sme_id", sme_id).execute()
        
        # IF NO OWNER: They are a brand new user who hasn't registered a business yet!
        if len(owner_res.data) == 0:
            return {
                "status": "Success",
                "data": {
                    "user": {
                        "name": current_user["name"], 
                        "email": current_user["email"], 
                        "sme_id": sme_id,
                        "preferences": current_user.get("preferences", {}) # Exposes Settings to frontend!
                    },
                    "has_business_profile": False,
                    "business": None,
                    "survival_history": [],
                    "growth_history": []
                }
            }
            
        owner_id = owner_res.data[0]["owner_id"]

        # 2. Fetch Business Record
        biz_res = supabase.table("business").select("*").eq("owner_id", owner_id).execute()
        business_data = biz_res.data[0] if len(biz_res.data) > 0 else None
        business_id = business_data["business_id"] if business_data else None

        # 3. Fetch Business Profile
        profile_data = None
        if business_id:
            profile_res = supabase.table("business_profile").select("*").eq("business_id", business_id).execute()
            profile_data = profile_res.data[0] if len(profile_res.data) > 0 else None

        # 4. Fetch Recent AI Predictions (Limit to top 5 for the dashboard UI)
        survival_history = []
        growth_history = []
        
        if business_id:
            surv_res = supabase.table("survival_prediction").select("*").eq("business_id", business_id).order("created_at", desc=True).limit(5).execute()
            survival_history = surv_res.data
            
            # For growth, we don't need the massive 'full_report' text on the main dashboard, just the numbers to draw a chart
            growth_res = supabase.table("growth_forecast").select("forecast_id, predicted_profit_cfa, growth_rate, created_at").eq("business_id", business_id).order("created_at", desc=True).limit(5).execute()
            growth_history = growth_res.data

        # Merge core business data with profile metrics for the React frontend
        full_business_payload = {**business_data, **profile_data} if business_data and profile_data else business_data

        # 5. Return the Master JSON Payload
        return {
            "status": "Success",
            "data": {
                "user": {
                    "name": current_user["name"], 
                    "email": current_user["email"], 
                    "sme_id": sme_id,
                    "preferences": current_user.get("preferences", {}) # Exposes Settings to frontend!
                },
                "has_business_profile": True,
                "business": full_business_payload,
                "survival_history": survival_history,
                "growth_history": growth_history
            }
        }

    except Exception as e:
        print(f"🔥 DASHBOARD ERROR: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard data.")


# ==========================================
# PROFILE UPDATE ENDPOINT
# ==========================================
@router.put("/update-profile")
def update_user_profile(payload: ProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """
    Allows the user to update their personal name and core business details 
    from the Profile Page in the React Dashboard.
    """
    try:
        sme_id = current_user["sme_id"]

        # 1. Format the name
        full_name = f"{payload.first_name or ''} {payload.last_name or ''}".strip()
        
        # 2. Update the SME table
        if full_name:
            supabase.table("sme").update({"name": full_name}).eq("sme_id", sme_id).execute()

        # 3. Safely update Owner and Business tables if they exist
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if owner_res.data:
            owner_id = owner_res.data[0]["owner_id"]
            
            # Update Owner (Name and Phone)
            owner_update = {}
            if full_name:
                owner_update["full_name"] = full_name
            if payload.phone is not None:
                owner_update["phone"] = payload.phone
            
            if owner_update:
                supabase.table("owner").update(owner_update).eq("owner_id", owner_id).execute()

            # Update Business (Name and Industry)
            biz_update = {}
            if payload.business_name:
                biz_update["name"] = payload.business_name
            if payload.industry:
                biz_update["industry"] = payload.industry
                
            if biz_update:
                supabase.table("business").update(biz_update).eq("owner_id", owner_id).execute()

        return {"status": "Success", "message": "Profile updated successfully!"}

    except Exception as e:
        print(f" PROFILE UPDATE ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")