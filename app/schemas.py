

from pydantic import BaseModel

# ==========================================
# AUTHENTICATION SCHEMAS
# ==========================================

class SMERegistration(BaseModel):
    name: str
    email: str 
    password: str

class SMELogin(BaseModel):
    email: str
    password: str

class ForgotPassword(BaseModel):
    email: str

class ResetPassword(BaseModel):
    email: str
    otp: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

# ==========================================
# BUSINESS SCHEMAS
# ==========================================

class BusinessRegistration(BaseModel):
    sme_id: str                 
    owner_full_name: str
    phone: str
    business_name: str
    industry: str               
    region: str                 
    sector: str                 
    startup_capital_cfa: float
    employees: int
    years_of_experience: int
    transport_cost_percentage: float
    energy_cost_percentage: float

class BusinessProfileUpdate(BaseModel):
    owner_full_name: str | None = None
    phone: str | None = None
    business_name: str | None = None
    industry: str | None = None
    region: str | None = None
    sector: str | None = None
    startup_capital_cfa: float | None = None
    employees: int | None = None
    years_of_experience: int | None = None
    transport_cost_percentage: float | None = None
    energy_cost_percentage: float | None = None

    # ==========================================
# AI PREDICTION SCHEMAS
# ==========================================

class PredictionRequest(BaseModel):
    business_id: str

    # ==========================================
# COMMUNICATION SCHEMAS
# ==========================================
class SubscribeRequest(BaseModel):
    email: str

class ContactRequest(BaseModel):
    name: str
    email: str
    subject: str
    message: str


class GoogleToken(BaseModel):
    access_token: str


class MobileRefreshRequest(BaseModel):
    refresh_token: str


class SupabaseEmailLinkExchange(BaseModel):
    access_token: str


# email link schema
class MagicLinkRequest(BaseModel):
    email: str

class MagicLinkVerify(BaseModel):
    email: str
    token: str    

# news letter
class BroadcastRequest(BaseModel):
    admin_password: str # Simple security check
    subject: str
    html_content: str    
