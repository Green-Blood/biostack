"""Recognising the document types BioStack accepts (a PDF, or a JPEG, PNG or HEIC photo) from their first bytes."""
from typing import NamedTuple

_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}


class SniffedDocument(NamedTuple):
    extension: str
    mime_type: str


KNOWN_DOCUMENTS = (
    SniffedDocument(".pdf", "application/pdf"),
    SniffedDocument(".jpg", "image/jpeg"),
    SniffedDocument(".png", "image/png"),
    SniffedDocument(".heic", "image/heic"),
)
PDF_KIND, JPEG_KIND, PNG_KIND, HEIC_KIND = KNOWN_DOCUMENTS


def sniff_document(content: bytes) -> SniffedDocument | None:
    if content.startswith(b"%PDF-"):
        return PDF_KIND
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG_KIND
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_KIND
    if content[4:8] == b"ftyp" and content[8:12] in _HEIC_BRANDS:
        return HEIC_KIND
    return None
