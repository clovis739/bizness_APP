from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

# ============================================================
# BizSense OS â€” Pydantic Schemas V2
# Extends V1 schemas with all fields required by V3 ML models
# V1 schemas are NOT modified â€” these are standalone additions
# ============================================================


# â”€â”€ Enums for strict validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RegionEnum(str, Enum):
    littoral   = "Littoral"
    centre     = "Centre"
    west       = "West"
    south_west = "South West"
    north_west = "North West"
    south      = "South"
    east       = "East"
    adamawa    = "Adamawa"
    north      = "North"
    far_north  = "Far North"


class SectorEnum(str, Enum):
    formal   = "Formal"
    informal = "Informal"


class IndustryEnum(str, Enum):
    agriculture  = "Agriculture"
    retail       = "Retail"
    services     = "Services"
    manufacturing = "Manufacturing"
    tech         = "Tech"
    construction = "Construction"
    transport    = "Transport"
    healthcare   = "Healthcare"
    education    = "Education"
    food_beverage = "Food & Beverage"


class EducationLevelEnum(str, Enum):
    none       = "None"
    primary    = "Primary"
    secondary  = "Secondary"
    university = "University"


class CompetitionLevelEnum(str, Enum):
    low       = "Low"
    medium    = "Medium"
    high      = "High"
    very_high = "Very High"


class FinancingMethodEnum(str, Enum):
    bank_loan          = "Bank Loan"
    government_subsidy = "Government Subsidy"
    supplier_credit    = "Supplier Credit"
    own_resources      = "Own Resources"
    tontine            = "Tontine"


class BusinessTypeEnum(str, Enum):
    sole_proprietorship = "Sole Proprietorship"
    partnership         = "Partnership"
    limited_company     = "Limited Company"
    cooperative         = "Cooperative"


# â”€â”€ V2 Business Registration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class BusinessRegistrationV2(BaseModel):
    """
    Collects all fields needed by the V3 ML model.
    Used by POST /api/v2/business/register
    """
    # Identity
    sme_id:          str
    owner_full_name: str
    phone:           str
    business_name:   str

    # Classification
    industry: IndustryEnum
    region:   RegionEnum
    sector:   SectorEnum
    business_type: BusinessTypeEnum = BusinessTypeEnum.sole_proprietorship

    # Financials
    startup_capital_cfa:        float = Field(..., gt=0, description="Startup capital in CFA Francs")
    transport_cost_percentage:  float = Field(..., ge=0, le=100)
    energy_cost_percentage:     float = Field(..., ge=0, le=100)

    # Staff & experience
    employees:           int   = Field(..., ge=1)
    years_of_experience: int   = Field(..., ge=0)
    owner_hours_per_week: int  = Field(default=40, ge=1, le=168)

    # â”€â”€ NEW V3 FIELDS â”€â”€
    year_started:            int  = Field(..., ge=1950, le=2026, description="Year the business was started")
    has_business_plan:       bool = Field(default=False)
    formal_financial_records: bool = Field(default=False)
    registered_formal:       bool = Field(default=False)

    owner_education_level: EducationLevelEnum = EducationLevelEnum.secondary
    competition_level:     CompetitionLevelEnum = CompetitionLevelEnum.medium
    access_to_financing:   str = Field(default="No", pattern="^(Yes|No)$")
    financing_method:      FinancingMethodEnum = FinancingMethodEnum.own_resources


class BusinessProfileUpdateV2(BaseModel):
    """
    All fields optional for PATCH updates.
    Used by PUT /api/v2/business/update-profile
    """
    owner_full_name:            Optional[str]   = None
    phone:                      Optional[str]   = None
    business_name:              Optional[str]   = None
    industry:                   Optional[IndustryEnum] = None
    region:                     Optional[RegionEnum]   = None
    sector:                     Optional[SectorEnum]   = None
    business_type:              Optional[BusinessTypeEnum] = None
    startup_capital_cfa:        Optional[float] = None
    transport_cost_percentage:  Optional[float] = None
    energy_cost_percentage:     Optional[float] = None
    employees:                  Optional[int]   = None
    years_of_experience:        Optional[int]   = None
    owner_hours_per_week:       Optional[int]   = None
    year_started:               Optional[int]   = None
    has_business_plan:          Optional[bool]  = None
    formal_financial_records:   Optional[bool]  = None
    registered_formal:          Optional[bool]  = None
    owner_education_level:      Optional[EducationLevelEnum] = None
    competition_level:          Optional[CompetitionLevelEnum] = None
    access_to_financing:        Optional[str]   = None
    financing_method:           Optional[FinancingMethodEnum] = None


# â”€â”€ V2 Prediction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PredictionRequestV2(BaseModel):
    """Used by POST /api/v2/predict/generate"""
    business_id: str


# â”€â”€ Re-export V1 auth schemas (no changes needed) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Auth, communication, and dashboard schemas are identical in
# V1 and V2 â€” import directly from app.schemas in routers

class IntelligenceRefreshRequest(BaseModel):
    """Controls how many items each trusted source should fetch during refresh."""
    limit_per_source: int = Field(default=20, ge=1, le=50)


class IntelligenceSourceCreate(BaseModel):
    """Creates a trusted online source for market intelligence ingestion."""
    source_name: str = Field(..., min_length=2, max_length=120)
    source_url: str = Field(..., min_length=8, max_length=600)
    source_type: str = Field(default="rss", pattern="^(rss|atom)$")
    category: str = Field(default="market", max_length=60)
    country: str = Field(default="Cameroon", max_length=80)
    is_active: bool = True


class IntelligenceItemResponse(BaseModel):
    """Public shape returned to web/mobile market intelligence screens."""
    id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    source_name: str
    original_url: str
    category: str
    industries: list[str] = []
    regions: list[str] = []
    country: Optional[str] = None
    published_at: Optional[str] = None
    fetched_at: Optional[str] = None
    credibility_score: Optional[float] = None
