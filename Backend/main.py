import os, sqlite3, secrets, hashlib, hmac, json, uuid, datetime as dt
from pathlib import Path
import cv2, numpy as np
from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File, Form
from pydantic import BaseModel, EmailStr, Field
from quality import assess

DB = os.getenv("DATABASE_PATH", "data/app.db"); UP = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
MODEL_PATH = os.getenv("MODEL_PATH", "")
SESSION_DAYS = 7
Path(DB).parent.mkdir(parents=True, exist_ok=True); UP.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="RetinaReach API")

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    try: yield c; c.commit()
    finally: c.close()

with sqlite3.connect(DB) as c:
    c.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
      role TEXT NOT NULL, org TEXT, pw_hash BLOB NOT NULL, salt BLOB NOT NULL, created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS screenings(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), participant_id TEXT NOT NULL,
      screening_date TEXT NOT NULL, eye TEXT NOT NULL, notes TEXT, image_path TEXT NOT NULL, quality TEXT, analysis TEXT,
      status TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);""")

def hpw(pw, salt): return hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
def th(t): return hashlib.sha256(t.encode()).hexdigest()
def now(): return dt.datetime.utcnow().isoformat()

class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=120); email: EmailStr; password: str = Field(min_length=10, max_length=200)
    role: str; org: str | None = None
class Login(BaseModel): email: EmailStr; password: str

def user(request: Request, c=Depends(db)):
    t = request.cookies.get("rr_session")
    r = t and c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires>?", (th(t), now())).fetchone()
    if not r: raise HTTPException(401, "Not signed in.")
    return r

def start(resp, c, uid):
    t = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions VALUES(?,?,?)", (th(t), uid, (dt.datetime.utcnow() + dt.timedelta(days=SESSION_DAYS)).isoformat()))
    resp.set_cookie("rr_session", t, httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "1") == "1", max_age=SESSION_DAYS * 86400)

def pub(u): return dict(id=u["id"], name=u["name"], email=u["email"], role=u["role"], org=u["org"])

@app.post("/api/auth/signup", status_code=201)
def signup(b: SignUp, resp: Response, c=Depends(db)):
    if not (any(x.isalpha() for x in b.password) and any(x.isdigit() for x in b.password)):
        raise HTTPException(422, "Password needs a letter and a number.")
    salt = os.urandom(16)
    try: cur = c.execute("INSERT INTO users(email,name,role,org,pw_hash,salt,created) VALUES(?,?,?,?,?,?,?)",
        (b.email.lower(), b.name, b.role, b.org, hpw(b.password, salt), salt, now()))
    except sqlite3.IntegrityError: raise HTTPException(409, "An account with this email already exists.")
    start(resp, c, cur.lastrowid); return pub(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())

@app.post("/api/auth/login")
def login(b: Login, resp: Response, c=Depends(db)):
    u = c.execute("SELECT * FROM users WHERE email=?", (b.email.lower(),)).fetchone()
    ok = u and hmac.compare_digest(hpw(b.password, u["salt"]), u["pw_hash"])
    if not ok: raise HTTPException(401, "Email or password is incorrect.")
    start(resp, c, u["id"]); return pub(u)

@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, resp: Response, c=Depends(db)):
    t = request.cookies.get("rr_session")
    if t: c.execute("DELETE FROM sessions WHERE token_hash=?", (th(t),))
    resp.delete_cookie("rr_session")

@app.get("/api/me")
def me(u=Depends(user)): return pub(u)

def decode(data: bytes):
    if len(data) > MAX_BYTES: raise HTTPException(413, f"Image is larger than {MAX_BYTES // 1048576} MB.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None: raise HTTPException(422, "File is not a readable JPEG or PNG image.")
    if min(img.shape[:2]) < 256: raise HTTPException(422, "Image is too small (minimum 256 px on the shorter side).")
    return img

def row(r):
    d = dict(r); d.pop("image_path"); d.pop("user_id")
    for k in ("quality", "analysis"): d[k] = json.loads(d[k]) if d[k] else None
    return d

def own(c, u, sid):  # ownership enforced here: other users' ids look like 404
    r = c.execute("SELECT * FROM screenings WHERE id=? AND user_id=?", (sid, u["id"])).fetchone()
    if not r: raise HTTPException(404, "Screening not found.")
    return r

@app.post("/api/screenings", status_code=201)
async def create(participant_id: str = Form(..., max_length=64), screening_date: str = Form(...), eye: str = Form(..., pattern="^(left|right|both)$"),
                 notes: str | None = Form(None, max_length=2000), image: UploadFile = File(...), u=Depends(user), c=Depends(db)):
    if image.content_type not in ("image/jpeg", "image/png"): raise HTTPException(415, "Only JPEG and PNG images are supported.")
    data = await image.read(MAX_BYTES + 1); img = decode(data)
    sid = uuid.uuid4().hex; d = UP / str(u["id"]); d.mkdir(exist_ok=True)
    p = d / f"{sid}.png"; cv2.imwrite(str(p), img)
    q = assess(img)
    c.execute("INSERT INTO screenings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (sid, u["id"], participant_id, screening_date, eye, notes, str(p), json.dumps(q), None, "quality_checked", now(), now()))
    return row(own(c, u, sid))

@app.get("/api/screenings")
def listing(u=Depends(user), c=Depends(db)):
    return [row(r) for r in c.execute("SELECT * FROM screenings WHERE user_id=? ORDER BY created DESC", (u["id"],))]

@app.get("/api/screenings/{sid}")
def one(sid: str, u=Depends(user), c=Depends(db)): return row(own(c, u, sid))

@app.post("/api/screenings/{sid}/quality-check")
def recheck(sid: str, u=Depends(user), c=Depends(db)):
    r = own(c, u, sid); q = assess(cv2.imread(r["image_path"]))
    c.execute("UPDATE screenings SET quality=?, updated=? WHERE id=?", (json.dumps(q), now(), sid)); return q

@app.post("/api/screenings/{sid}/analyze")
def analyze(sid: str, u=Depends(user), c=Depends(db)):
    r = own(c, u, sid)
    if json.loads(r["quality"])["status"] == "recapture_recommended":
        raise HTTPException(409, "Image failed the quality gate. Recapture before analysis.")
    if not MODEL_PATH or not Path(MODEL_PATH).exists():
        raise HTTPException(503, "Screening model is not installed. No prediction was produced.")  # never fabricate
    raise HTTPException(501, "Model inference is added in Stage 4.")
