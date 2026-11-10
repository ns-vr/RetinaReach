from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.config import UPLOAD_DIR, MAX_UPLOAD_MB, CORS_ORIGINS, JWT_SECRET
from app.database import Base, engine, get_db
from app.models import User, Screening
from app.schemas import RegisterRequest, LoginRequest, UserOut, TokenOut, ScreeningOut, HealthOut
from app.security import hash_password, verify_password, create_access_token, decode_access_token
from app.quality import inspect_image
from app.inference import infer_retinal_image

app = FastAPI(
    title="RetinaReach API",
    version="1.0.0",
    description="Backend API prototype for image-quality-aware retinal screening workflows. Not a diagnostic device."
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)

def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired. Please sign in again.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user

def to_screening_out(row: Screening):
    return ScreeningOut(
        id=row.id, patient_label=row.patient_label, eye=row.eye,
        image_filename=row.image_filename, image_width=row.image_width, image_height=row.image_height,
        quality_score=row.quality_score, quality_status=row.quality_status,
        quality_notes=[x for x in row.quality_notes.split("\n") if x],
        inference_status=row.inference_status, prediction_label=row.prediction_label,
        prediction_confidence=row.prediction_confidence, review_required=bool(row.review_required),
        created_at=row.created_at,
    )

@app.get("/api/health", response_model=HealthOut)
def health():
    configured = bool(__import__("app.config", fromlist=["INFERENCE_URL"]).INFERENCE_URL)
    return HealthOut(
        status="ok", version="1.0.0", inference_configured=configured,
        note="Image-quality checks are heuristic. This API does not itself provide a validated diagnosis."
    )

@app.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    if "CHANGE-ME" in JWT_SECRET:
        # Allow local development, but loudly avoid silently shipping the default key.
        import os
        if os.getenv("RETINAREACH_ALLOW_INSECURE_DEV", "1") != "1":
            raise HTTPException(status_code=500, detail="Set RETINAREACH_JWT_SECRET before using this server.")
    user = User(email=email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))

@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))

@app.get("/api/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)

@app.post("/api/screenings", response_model=ScreeningOut, status_code=201)
async def create_screening(
    file: UploadFile = File(...),
    eye: str = Form("unknown"),
    patient_label: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if eye not in {"left", "right", "unknown"}:
        raise HTTPException(status_code=422, detail="eye must be left, right, or unknown.")
    filename = Path(file.filename or "retinal-image").name
    content_type = (file.content_type or "").lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp", "image/tiff"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, WEBP, or TIFF image.")
    raw = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Image exceeds the {MAX_UPLOAD_MB} MB upload limit.")
    try:
        quality = inspect_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Run optional model service only for images that pass a basic quality gate.
    if quality["status"] == "acceptable":
        inference = infer_retinal_image(raw, filename)
    else:
        inference = {"status": "skipped_quality_gate", "label": None, "confidence": None}

    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
        suffix = ".img"
    stored_name = f"{uuid4().hex}{suffix}"
    target = UPLOAD_DIR / stored_name
    target.write_bytes(raw)

    notes = list(quality["notes"])
    if inference["status"] == "not_configured":
        notes.append("No inference model is connected. No retinal disease prediction was produced.")
    elif inference["status"] == "error":
        notes.append("The configured inference service could not return a usable result.")

    row = Screening(
        owner_id=user.id,
        patient_label=(patient_label.strip()[:100] if patient_label and patient_label.strip() else None),
        eye=eye, image_filename=filename[:255], image_path=str(target),
        image_width=quality["width"], image_height=quality["height"],
        quality_score=quality["score"], quality_status=quality["status"],
        quality_notes="\n".join(notes),
        inference_status=inference["status"], prediction_label=inference["label"],
        prediction_confidence=inference["confidence"],
        review_required=1 if quality["status"] != "acceptable" or inference["status"] != "complete" else 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result = to_screening_out(row)
    # Include non-clinical numeric image metrics for UI visualization.
    result_payload = result.model_dump()
    result_payload["quality_metrics"] = quality["metrics"]
    return result_payload

@app.get("/api/screenings", response_model=list[ScreeningOut])
def list_screenings(
    limit: int = 50, offset: int = 0,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    rows = (db.query(Screening).filter(Screening.owner_id == user.id)
            .order_by(desc(Screening.created_at)).offset(offset).limit(limit).all())
    return [to_screening_out(row) for row in rows]

@app.get("/api/screenings/{screening_id}", response_model=ScreeningOut)
def get_screening(screening_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(Screening).filter(Screening.id == screening_id, Screening.owner_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Screening record not found.")
    return to_screening_out(row)

@app.get("/api/review-queue", response_model=list[ScreeningOut])
def review_queue(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Screening).filter(Screening.owner_id == user.id, Screening.review_required == 1)
            .order_by(desc(Screening.created_at)).limit(100).all())
    return [to_screening_out(row) for row in rows]

@app.delete("/api/screenings/{screening_id}", status_code=204)
def delete_screening(screening_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(Screening).filter(Screening.id == screening_id, Screening.owner_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Screening record not found.")
    try:
        Path(row.image_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(row)
    db.commit()
    return None
