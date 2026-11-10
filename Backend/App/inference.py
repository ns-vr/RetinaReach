import os
import requests
from app.config import INFERENCE_URL

def infer_retinal_image(image_bytes: bytes, filename: str):
    """
    Optional adapter for a separately deployed, evaluated model service.
    Expected response JSON:
      {"status":"complete","prediction_label":"...","prediction_confidence":0.0}
    The model service must implement its own validation and return calibrated,
    documented outputs. No diagnosis is fabricated if no service is configured.
    """
    if not INFERENCE_URL:
        return {"status": "not_configured", "label": None, "confidence": None}
    try:
        response = requests.post(
            INFERENCE_URL,
            files={"file": (filename, image_bytes, "application/octet-stream")},
            timeout=(3, 20),
        )
        response.raise_for_status()
        payload = response.json()
        label = payload.get("prediction_label")
        confidence = payload.get("prediction_confidence")
        status = payload.get("status")
        if status != "complete" or not isinstance(label, str):
            return {"status": "error", "label": None, "confidence": None}
        if confidence is not None:
            confidence = float(confidence)
            if not 0 <= confidence <= 1:
                return {"status": "error", "label": None, "confidence": None}
        return {"status": "complete", "label": label[:100], "confidence": confidence}
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return {"status": "error", "label": None, "confidence": None}
