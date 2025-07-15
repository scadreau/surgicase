# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:11:06

# core/models.py
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

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
    message_pref: Optional[str] = None
    states_licensed: Optional[str] = None
    documents: Optional[List[UserDocument]] = None

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
    procedure_codes: Optional[List[str]] = None

class CaseRequest(BaseModel):
    case_id: str

# Facility Models
class FacilityCreate(BaseModel):
    user_id: str
    facility_name: str

class FacilityRequest(BaseModel):
    facility_id: int

class FacilitiesRequest(BaseModel):
    user_id: str

# Surgeon Models
class SurgeonCreate(BaseModel):
    user_id: str
    first_name: str
    last_name: str

class SurgeonRequest(BaseModel):
    surgeon_id: int

class SurgeonsRequest(BaseModel):
    user_id: str