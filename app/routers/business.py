

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

        owner_payload = {
            "sme_id": data.sme_id,
            "full_name": data.owner_full_name,
            "username": sme_account["email"],
            "password_hash": sme_account["password_hash"],
            "phone": data.phone,
        }

        # Reuse the existing owner record when this SME already created one.
        owner_res = supabase.table("owner").select("*").eq("sme_id", data.sme_id).execute()
        owner_by_username_res = supabase.table("owner").select("*").eq("username", sme_account["email"]).execute()

        existing_owner = None
        if owner_res.data:
            existing_owner = owner_res.data[0]
        elif owner_by_username_res.data:
            existing_owner = owner_by_username_res.data[0]

        if existing_owner:
            owner_id = existing_owner["owner_id"]
            supabase.table("owner").update({
                "sme_id": data.sme_id,
                "full_name": data.owner_full_name,
                "phone": data.phone,
            }).eq("owner_id", owner_id).execute()
        else:
            try:
                created_owner = supabase.table("owner").insert(owner_payload).execute()
                owner_id = created_owner.data[0]["owner_id"]
            except Exception as owner_error:
                # If another row already exists for this username, recover by reusing it.
                if "owner_username_key" not in str(owner_error):
                    raise owner_error

                fallback_owner_res = supabase.table("owner").select("*").eq("username", sme_account["email"]).execute()
                if not fallback_owner_res.data:
                    raise owner_error

                owner_id = fallback_owner_res.data[0]["owner_id"]
                supabase.table("owner").update({
                    "sme_id": data.sme_id,
                    "full_name": data.owner_full_name,
                    "phone": data.phone,
                }).eq("owner_id", owner_id).execute()

        business_payload = {
            "owner_id": owner_id,
            "name": data.business_name,
            "industry": data.industry,
        }

        business_lookup = supabase.table("business").select("*").eq("owner_id", owner_id).execute()
        if business_lookup.data:
            business_id = business_lookup.data[0]["business_id"]
            supabase.table("business").update(business_payload).eq("business_id", business_id).execute()
            message = "Business profile updated!"
        else:
            business_res = supabase.table("business").insert(business_payload).execute()
            business_id = business_res.data[0]["business_id"]
            message = "Business profile created!"

        profile_payload = {
            "business_id": business_id,
            "region": data.region,
            "sector": data.sector,
            "startup_capital_cfa": data.startup_capital_cfa,
            "employees": data.employees,
            "years_of_experience": data.years_of_experience,
            "transport_cost_percentage": data.transport_cost_percentage,
            "energy_cost_percentage": data.energy_cost_percentage,
        }

        existing_profile = supabase.table("business_profile").select("*").eq("business_id", business_id).execute()
        if existing_profile.data:
            supabase.table("business_profile").update(profile_payload).eq("business_id", business_id).execute()
        else:
            supabase.table("business_profile").insert(profile_payload).execute()

        return {"status": "Success", "message": message, "business_id": business_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
