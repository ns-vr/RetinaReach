from io import BytesIO
import numpy as np
from PIL import Image, ImageStat, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}

def inspect_image(raw: bytes) -> dict:
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("The uploaded file is not a readable image.") from exc

    width, height = image.size
    if width < 128 or height < 128:
        raise ValueError("Image is too small. Upload an image at least 128 × 128 pixels.")
    arr = np.asarray(image, dtype=np.float32)
    gray = arr.mean(axis=2)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    # Simple Laplacian-like edge proxy using neighboring pixels; not a clinical quality metric.
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    sharpness = float(lap.var()) if lap.size else 0.0
    notes = []
    score = 100.0

    if brightness < 35:
        notes.append("Image appears very dark; consider improving illumination.")
        score -= 30
    elif brightness > 225:
        notes.append("Image appears very bright; highlights may obscure detail.")
        score -= 25
    if contrast < 18:
        notes.append("Low contrast detected; retinal detail may be difficult to assess.")
        score -= 20
    if sharpness < 25:
        notes.append("Image may be blurred; consider retaking it with steadier focus.")
        score -= 25
    if min(width, height) < 512:
        notes.append("Resolution is relatively low; use a higher-resolution image if available.")
        score -= 10

    score = max(0.0, min(100.0, score))
    if score >= 75:
        status = "acceptable"
    elif score >= 50:
        status = "review"
    else:
        status = "recapture"

    return {
        "width": width, "height": height, "score": round(score, 1),
        "status": status, "notes": notes,
        "metrics": {"mean_brightness": round(brightness, 2),
                    "contrast_std": round(contrast, 2),
                    "edge_variance_proxy": round(sharpness, 2)},
    }
