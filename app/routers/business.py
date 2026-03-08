

from fastapi import APIRouter, HTTPException
from app.database import supabase
from app.schemas import BusinessRegistration

# Initialize the Router
router = APIRouter(
    prefix="/api/v1/business",
    tags=["Business Management"]
)

@router.post("/register")
def register_business(data: BusinessRegistration):
    try:
        # Check SME
        sme_res = supabase.table("sme").select("*").eq("sme_id", data.sme_id).execute()
        if len(sme_res.data) == 0:
            raise HTTPException(status_code=404, detail="SME account not found.")
        sme_account = sme_res.data[0]

        # Create Owner
        new_owner = {"sme_id": data.sme_id, "full_name": data.owner_full_name, "username": sme_account["email"], "password_hash": sme_account["password_hash"], "phone": data.phone}
        owner_res = supabase.table("owner").insert(new_owner).execute()
        owner_id = owner_res.data[0]["owner_id"]

        # Create Business
        new_business = {"owner_id": owner_id, "name": data.business_name, "industry": data.industry}
        business_res = supabase.table("business").insert(new_business).execute()
        business_id = business_res.data[0]["business_id"]

        # Create Business Profile
        new_profile = {
            "business_id": business_id, "region": data.region, "sector": data.sector,
            "startup_capital_cfa": data.startup_capital_cfa, "employees": data.employees,
            "years_of_experience": data.years_of_experience, "transport_cost_percentage": data.transport_cost_percentage,
            "energy_cost_percentage": data.energy_cost_percentage
        }
        supabase.table("business_profile").insert(new_profile).execute()

        return {"status": "Success", "message": "Business profile created!", "business_id": business_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))