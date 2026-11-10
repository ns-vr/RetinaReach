from io import BytesIO
from PIL import Image
from app.quality import inspect_image

def test_inspect_image_returns_quality_fields():
    buf = BytesIO()
    Image.new("RGB", (640, 640), (120, 120, 120)).save(buf, format="JPEG")
    result = inspect_image(buf.getvalue())
    assert result["width"] == 640
    assert result["height"] == 640
    assert result["status"] in {"acceptable", "review", "recapture"}
    assert 0 <= result["score"] <= 100
