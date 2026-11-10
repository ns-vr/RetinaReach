# RetinaReach Backend API

A FastAPI backend prototype for RetinaReach. It provides account registration/login, token-protected endpoints, image upload, heuristic image-quality checks, records, a review queue, and deletion.

**Clinical safety:** this is not a validated medical device and does not diagnose diabetic retinopathy. The built-in image-quality score uses basic image statistics only. Disease prediction remains unavailable unless you connect a separately deployed, evaluated model service. Do not use real patient images until privacy, consent, access controls, retention, encryption, deployment security, and applicable legal/regulatory requirements have been reviewed.

## 1. Run locally

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Set `RETINAREACH_JWT_SECRET` in `.env` to a long random secret. Then load environment variables (PowerShell example):

```powershell
Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object {
  $name, $value = $_ -split '=', 2
  Set-Item -Path "Env:$name" -Value $value
}
uvicorn app.main:app --reload
```

Open:
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

The SQLite database and uploaded images are stored in `data/` by default. Keep that directory private.

## 2. API overview

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/health` | Service status and model configuration | No |
| POST | `/api/auth/register` | Create account | No |
| POST | `/api/auth/login` | Sign in | No |
| GET | `/api/me` | Current user | Bearer token |
| POST | `/api/screenings` | Upload image and create record | Bearer token |
| GET | `/api/screenings` | List the current user's records | Bearer token |
| GET | `/api/screenings/{id}` | Get one record | Bearer token |
| GET | `/api/review-queue` | Records requiring review | Bearer token |
| DELETE | `/api/screenings/{id}` | Delete record and stored image | Bearer token |

### Register

```json
{
  "email": "demo@example.com",
  "display_name": "Demo User",
  "password": "use-a-long-password"
}
```

Returns `access_token` and `user`.

### Upload a screening

Send `multipart/form-data` with:
- `file`: JPEG, PNG, WEBP, or TIFF
- `eye`: `left`, `right`, or `unknown`
- `patient_label`: optional local label, do not use identifying information in demos

Include header `Authorization: Bearer YOUR_ACCESS_TOKEN`.

## 3. Connect your frontend

Use `http://127.0.0.1:8000` as the API base URL during local development. Save `access_token` after register/login and send it as a Bearer token on protected requests.

Example JavaScript:

```js
const API_BASE = "http://127.0.0.1:8000";

export async function signIn(email, password) {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Sign in failed");
  return data; // store access_token using your app's auth strategy
}

export async function uploadScreening(token, file, eye = "unknown", patientLabel = "") {
  const form = new FormData();
  form.append("file", file);
  form.append("eye", eye);
  if (patientLabel) form.append("patient_label", patientLabel);

  const response = await fetch(`${API_BASE}/api/screenings`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Upload failed");
  return data;
}

export async function getScreenings(token) {
  const response = await fetch(`${API_BASE}/api/screenings`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not load records");
  return data;
}
```

Do not set the multipart `Content-Type` header manually; the browser must add its boundary.

## 4. Optional model integration

Set `RETINAREACH_INFERENCE_URL` to your own model-serving endpoint. RetinaReach will POST the uploaded image as multipart field `file`. The model service should return:

```json
{
  "status": "complete",
  "prediction_label": "your-model-output",
  "prediction_confidence": 0.82
}
```

This is an integration contract, not a model. Only connect a model after evaluating it on appropriate held-out data, documenting intended use and limitations, and setting a safe review workflow. The API skips inference when the heuristic quality gate says `review` or `recapture`; this gate is not clinically validated.

## 5. Before deployment

This is a development starter, not production-ready clinical infrastructure. Before deployment:
- replace the development JWT secret and use a secret manager;
- use HTTPS, managed database, private object storage, backups, and encryption at rest;
- add rate limiting, login throttling, email verification, password reset, and audit logging;
- add migrations, retention/deletion policies, malware/content scanning, monitoring, and automated tests;
- restrict CORS to the exact deployed frontend origin;
- do not store real patient data until privacy, consent, regulatory, and security requirements have been assessed;
- review authentication architecture and consider secure, HttpOnly cookies for browser sessions;
- evaluate any ML model and avoid presenting its output as a diagnosis without appropriate clinical validation and authorization.
