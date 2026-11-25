"""HEIC photos (iPhone default) as JPEG, because browsers cannot show HEIC."""
import io

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()
HEIC_MIME = "image/heic"


def to_jpeg(data: bytes, max_side: int = 2400) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=88)
        return out.getvalue()
