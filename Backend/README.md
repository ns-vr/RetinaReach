# RetinaReach backend (Stage 2)
    pip install -r requirements.txt
    cp .env.example .env && export $(grep -v '^#' .env | cut -d' ' -f1 | xargs)
    uvicorn main:app --reload      # docs at /docs
Implemented: signup/login/logout/me (scrypt hashes, hashed httpOnly session tokens), screenings with per-user ownership (other users get 404),
upload validation (JPEG/PNG, size, decodability), OpenCV quality gate (blur, illumination, contrast, framing).
Not implemented: model inference (analyze returns 503 until weights exist), PATCH/export endpoints, password reset, CSRF tokens.
Quality thresholds in quality.py are uncalibrated heuristics. Test them on labeled images.
