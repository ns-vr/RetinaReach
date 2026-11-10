from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    screenings = relationship("Screening", back_populates="owner", cascade="all, delete-orphan")

class Screening(Base):
    __tablename__ = "screenings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    patient_label = Column(String(100), nullable=True)
    eye = Column(String(10), nullable=False, default="unknown")
    image_filename = Column(String(255), nullable=False)
    image_path = Column(Text, nullable=False)
    image_width = Column(Integer, nullable=False)
    image_height = Column(Integer, nullable=False)
    quality_score = Column(Float, nullable=False)
    quality_status = Column(String(30), nullable=False)
    quality_notes = Column(Text, nullable=False, default="")
    inference_status = Column(String(40), nullable=False, default="not_configured")
    prediction_label = Column(String(100), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    review_required = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    owner = relationship("User", back_populates="screenings")
