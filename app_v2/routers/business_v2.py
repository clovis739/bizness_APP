from fastapi import APIRouter, HTTPException, Depends
from app.database import supabase
from app.routers.dashboard import get_current_user
from app_v2.schemas_v2 import BusinessRegistrationV2, BusinessProfileUpdateV2

# ============================================================
# BizSense OS — Business Router V2
# Saves all V3 fields to business_profile_v2 table.
# Reuses the existing owner + business table from V1
# (no structural changes to V1 tables).
# ============================================================

router = APIRouter(
    prefix="/api/v2/business",
    tags=["Business V2"]
)


@router.post("/register")
def register_business_v2(
    data: BusinessRegistrationV2,
    current_user: dict = Depends(get_current_user)
):
    """
    Registers or updates a business profile with all V3 ML fields.
    Writes to business_profile_v2 — never touches business_profile (V1).
    Requires authentication.
    """
    try:
        # ── Security: confirm the sme_id matches the logged-in user ──
        if current_user["sme_id"] != data.sme_id:
            raise HTTPException(status_code=403, detail="Access Denied: sme_id mismatch.")

        # ── Step 1: Verify SME account exists ──
        sme_res = supabase.table("sme").select("*").eq("sme_id", data.sme_id).execute()
        if not sme_res.data:
            raise HTTPException(status_code=404, detail="SME account not found.")
        sme_account = sme_res.data[0]

        # ── Step 2: Upsert owner record ──
        owner_payload = {
            "sme_id":        data.sme_id,
            "full_name":     data.owner_full_name,
            "username":      sme_account["email"],
            "password_hash": sme_account["password_hash"],
            "phone":         data.phone,
        }

        owner_res = supabase.table("owner").select("*").eq("sme_id", data.sme_id).execute()
        if owner_res.data:
            owner_id = owner_res.data[0]["owner_id"]
            supabase.table("owner").update({
                "full_name": data.owner_full_name,
                "phone":     data.phone,
            }).eq("owner_id", owner_id).execute()
        else:
            try:
                created = supabase.table("owner").insert(owner_payload).execute()
                owner_id = created.data[0]["owner_id"]
            except Exception as owner_err:
                # Recover from username uniqueness conflict
                if "owner_username_key" not in str(owner_err):
                    raise owner_err
                fallback = supabase.table("owner").select("*").eq("username", sme_account["email"]).execute()
                if not fallback.data:
                    raise owner_err
                owner_id = fallback.data[0]["owner_id"]
                supabase.table("owner").update({
                    "full_name": data.owner_full_name,
                    "phone":     data.phone,
                }).eq("owner_id", owner_id).execute()

        # ── Step 3: Upsert business record ──
        # Match by owner_id + business_name so each unique name creates its own
        # business record, allowing a single owner to manage multiple businesses.
        business_payload = {
            "owner_id": owner_id,
            "name":     data.business_name,
            "industry": data.industry.value,
        }
        biz_lookup = (
            supabase.table("business")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("name", data.business_name)
            .execute()
        )
        if biz_lookup.data:
            business_id = biz_lookup.data[0]["business_id"]
            supabase.table("business").update({"industry": data.industry.value}).eq("business_id", business_id).execute()
            message = "Business V2 profile updated!"
        else:
            biz_res = supabase.table("business").insert(business_payload).execute()
            business_id = biz_res.data[0]["business_id"]
            message = "Business V2 profile created!"

        # ── Step 4: Upsert business_profile_v2 (new table, all V3 fields) ──
        profile_v2_payload = {
            "business_id":               business_id,
            "region":                    data.region.value,
            "sector":                    data.sector.value,
            "startup_capital_cfa":       data.startup_capital_cfa,
            "employees":                 data.employees,
            "years_of_experience":       data.years_of_experience,
            "transport_cost_percentage": data.transport_cost_percentage,
            "energy_cost_percentage":    data.energy_cost_percentage,
            # V3 new fields
            "year_started":              data.year_started,
            "has_business_plan":         data.has_business_plan,
            "formal_financial_records":  data.formal_financial_records,
            "registered_formal":         data.registered_formal,
            "owner_education_level":     data.owner_education_level.value,
            "competition_level":         data.competition_level.value,
            "access_to_financing":       data.access_to_financing,
            "financing_method":          data.financing_method.value,
            "owner_hours_per_week":      data.owner_hours_per_week,
            "business_type":             data.business_type.value,
        }

        existing_v2 = supabase.table("business_profile_v2").select("*").eq("business_id", business_id).execute()
        if existing_v2.data:
            supabase.table("business_profile_v2").update(profile_v2_payload).eq("business_id", business_id).execute()
        else:
            supabase.table("business_profile_v2").insert(profile_v2_payload).execute()

        return {
            "status":      "Success",
            "message":     message,
            "business_id": business_id,
            "api_version": "v2"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Business V2 Registration Error: {str(e)}")


@router.put("/update-profile/{business_id}")
def update_business_profile_v2(
    business_id: str,
    data: BusinessProfileUpdateV2,
    current_user: dict = Depends(get_current_user)
):
    """
    Partially updates a V2 business profile.
    Only the fields provided in the request body are updated.
    """
    try:
        sme_id = current_user["sme_id"]

        # Security: verify ownership
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: No owner profile found.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        # Build update payload from only the provided fields
        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            return {"status": "Success", "message": "Nothing to update."}

        # Convert enum values to strings
        enum_fields = [
            "industry", "region", "sector", "business_type",
            "owner_education_level", "competition_level", "financing_method"
        ]
        for field in enum_fields:
            if field in update_data and hasattr(update_data[field], "value"):
                update_data[field] = update_data[field].value

        # Update business table fields if applicable
        biz_fields = {k: v for k, v in update_data.items() if k in ["business_name", "industry"]}
        if "business_name" in biz_fields:
            biz_fields["name"] = biz_fields.pop("business_name")
        if biz_fields:
            supabase.table("business").update(biz_fields).eq("business_id", business_id).execute()

        # Update profile_v2 fields
        profile_fields = {k: v for k, v in update_data.items() if k not in ["business_name"]}
        if profile_fields:
            existing = supabase.table("business_profile_v2").select("business_id").eq("business_id", business_id).execute()
            if existing.data:
                supabase.table("business_profile_v2").update(profile_fields).eq("business_id", business_id).execute()
            else:
                profile_fields["business_id"] = business_id
                supabase.table("business_profile_v2").insert(profile_fields).execute()

        return {"status": "Success", "message": "Business V2 profile updated!", "api_version": "v2"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile Update Error: {str(e)}")
