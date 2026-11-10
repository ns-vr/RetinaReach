import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("RETINAREACH_DATA_DIR", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'retinareach.db').as_posix()}")
JWT_SECRET = os.getenv("RETINAREACH_JWT_SECRET", "CHANGE-ME-before-deployment-use-a-long-random-secret")
JWT_EXPIRE_MINUTES = int(os.getenv("RETINAREACH_JWT_EXPIRE_MINUTES", "60"))
MAX_UPLOAD_MB = int(os.getenv("RETINAREACH_MAX_UPLOAD_MB", "10"))
CORS_ORIGINS = [x.strip() for x in os.getenv(
    "RETINAREACH_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5500"
).split(",") if x.strip()]
INFERENCE_URL = os.getenv("RETINAREACH_INFERENCE_URL", "").strip()
