"""Heuristic image-quality gate. Thresholds are UNCALIBRATED starting points:
validate them on labeled fundus images before relying on them."""
import cv2, numpy as np

T = dict(blur_bad=40.0, blur_warn=100.0, dark=40.0, bright=200.0, contrast_bad=25.0, field_bad=0.35, field_warn=0.5)

def assess(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    small = cv2.resize(img, (512, int(512 * h / w))) if w > 512 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mask = gray > 15                                   # non-black = retinal field
    field = float(mask.mean())
    mean = float(gray[mask].mean()) if mask.any() else 0.0
    contrast = float(gray[mask].std()) if mask.any() else 0.0
    cx_off = 0.0
    if mask.any():
        xs = np.where(mask.any(axis=0))[0]
        cx_off = abs(((xs.min() + xs.max()) / 2) / gray.shape[1] - 0.5)
    bad, warn = [], []
    if blur < T["blur_bad"]: bad.append(("blur", "Image is out of focus. Stabilize the camera, refocus, and capture again."))
    elif blur < T["blur_warn"]: warn.append(("blur", "Image is slightly soft. Check focus."))
    if mean < T["dark"]: bad.append(("illumination", "Image is too dark. Increase illumination and capture again."))
    elif mean > T["bright"]: bad.append(("illumination", "Image is overexposed. Reduce illumination and capture again."))
    if contrast < T["contrast_bad"]: warn.append(("contrast", "Low contrast. Check lighting and lens cleanliness."))
    if field < T["field_bad"]: bad.append(("framing", "Retinal field is mostly missing. Center the retina in the frame and capture again."))
    elif field < T["field_warn"] or cx_off > 0.12: warn.append(("framing", "Retina is partly cropped or off-center. Re-center if possible."))
    status = "recapture_recommended" if bad else "review_recommended" if warn else "usable"
    return dict(status=status, metrics=dict(laplacian_variance=round(blur, 1), mean_brightness=round(mean, 1),
        contrast_std=round(contrast, 1), field_fraction=round(field, 2), horizontal_offset=round(cx_off, 2)),
        reasons=[{"check": c, "message": m} for c, m in bad + warn], thresholds=T,
        limitation="Generic computer-vision checks; not a clinical image-quality standard.")
