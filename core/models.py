# Created: 2025-07-15 09:20:13
# Last Modified: 2025-10-17 18:00:35
# Author: Scott Cadreau

# core/models.py
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

# User Models
class UserDocument(BaseModel):
    document_type: str
    document_name: str

class UserCreate(BaseModel):
    user_id: str
    user_email: EmailStr
    first_name: str
    last_name: str
    addr1: str
    addr2: str = ""
    city: str
    state: str
    zipcode: str
    telephone: str
    user_npi: str
    referred_by_user: str = ""
    message_pref: str
    states_licensed: str
    timezone: Optional[str] = None
    credentials: Optional[str] = None
    ins_exp_date: Optional[str] = None
    documents: Optional[List[UserDocument]] = None

class UserUpdate(BaseModel):
    user_id: str
    user_email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    addr1: Optional[str] = None
    addr2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    telephone: Optional[str] = None
    user_npi: Optional[str] = None
    referred_by_user: Optional[str] = None
    user_type: Optional[int] = None
    message_pref: Optional[str] = None
    states_licensed: Optional[str] = None
    timezone: Optional[str] = None
    credentials: Optional[str] = None
    ins_exp_date: Optional[str] = None
    documents: Optional[List[UserDocument]] = None
    last_login_dt: Optional[datetime] = None
    max_case_status: Optional[int] = None
    user_tier: Optional[int] = None

class UserRequest(BaseModel):
    user_id: str

# Case Models
class PatientInfo(BaseModel):
    first: str
    last: str
    ins_provider: str

class CaseCreate(BaseModel):
    user_id: str
    case_id: str
    case_date: str  # ISO date string
    surgeon_id: str
    facility_id: str
    patient: PatientInfo
    demo_file: Optional[str] = None
    note_file: Optional[str] = None
    misc_file: Optional[str] = None
    procedure_codes: Optional[List[str]] = None
    force_duplicate: Optional[bool] = False
    patient_dob: Optional[str] = None

class CaseUpdate(BaseModel):
    case_id: str
    user_id: Optional[str] = None
    case_date: Optional[str] = None
    surgeon_id: Optional[str] = None
    facility_id: Optional[str] = None
    patient_first: Optional[str] = None
    patient_last: Optional[str] = None
    ins_provider: Optional[str] = None
    demo_file: Optional[str] = None
    note_file: Optional[str] = None
    misc_file: Optional[str] = None
    admin_file: Optional[str] = None
    procedure_codes: Optional[List[str]] = None
    patient_dob: Optional[str] = None
class CaseRequest(BaseModel):
    case_id: str

# Facility Models
class FacilityCreate(BaseModel):
    user_id: str
    facility_name: str
    facility_npi: int
    facility_addr: str
    facility_city: str
    facility_state: str
    facility_zip: str

class FacilityRequest(BaseModel):
    facility_id: int

class FacilitiesRequest(BaseModel):
    user_id: str

# Surgeon Models
class SurgeonCreate(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    surgeon_npi: int
    surgeon_addr: str
    surgeon_city: str
    surgeon_state: str
    surgeon_zip: str

class SurgeonRequest(BaseModel):
    surgeon_id: int

class SurgeonsRequest(BaseModel):
    user_id: str

# Log Request Models
class LogRequestModel(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str | None = None
    endpoint: str
    method: str
    request_payload: str | None = None
    query_params: str | None = None
    response_status: int
    response_payload: str | None = None
    execution_time_ms: int
    error_message: str | None = None
    client_ip: str | None = None

# Bulk Case Status Update Models
class BulkCaseStatusUpdate(BaseModel):
    case_ids: List[str]
    new_status: int
    force: Optional[bool] = False

# List Addition Models for add_to_lists.py
class UserTypeCreate(BaseModel):
    user_type: int
    user_type_desc: str
    user_max_case_status: int
    user_id: str  # For authorization

class CaseStatusCreate(BaseModel):
    case_status: int
    case_status_desc: str
    user_id: str  # For authorization

class UserDocTypeCreate(BaseModel):
    doc_type: str
    doc_prefix: str
    user_id: str  # For authorization

class FaqCreate(BaseModel):
    user_type: int
    faq_header: str
    faq_text: str
    display_order: int
    user_id: str  # For authorization

class PayTierBucket(BaseModel):
    bucket: str  # This will map to code_bucket in the database
    pay_amount: float

class PayTierCreate(BaseModel):
    tier: int
    buckets: List[PayTierBucket]  # Multiple bucket/pay_amount combinations
    user_id: str  # For authorization

# Password Management Models
class PasswordChange(BaseModel):
    user_id: str
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")
