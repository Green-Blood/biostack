import io

import pillow_heif
from PIL import Image

from services.heic import to_jpeg


def test_heic_becomes_a_jpeg():
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "HEIF")
    out = to_jpeg(buf.getvalue())
    assert out[:3] == b"\xff\xd8\xff" and Image.open(io.BytesIO(out)).size == (40, 30)
