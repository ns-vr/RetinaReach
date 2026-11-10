from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class ScreeningOut(BaseModel):
    id: int
    patient_label: Optional[str]
    eye: str
    image_filename: str
    image_width: int
    image_height: int
    quality_score: float
    quality_status: str
    quality_notes: list[str]
    inference_status: str
    prediction_label: Optional[str]
    prediction_confidence: Optional[float]
    review_required: bool
    created_at: datetime

class HealthOut(BaseModel):
    status: str
    version: str
    inference_configured: bool
    note: str
