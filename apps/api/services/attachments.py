"""Keeping original files (scans, reports, photos) with the records they belong to."""
import hashlib
from pathlib import Path

from sqlmodel import Session, select

from config import settings
from db.models import RecordAttachment
from services.documents import sniff_document


class UnsupportedAttachment(Exception):
    """The file is not a PDF or a JPEG, PNG or HEIC photo."""


def attach_bytes(session: Session, record_id: int, content: bytes, filename: str) -> RecordAttachment:
    """Store `content` in data/attachments (once per distinct content) and link it to the record. Idempotent."""
    kind = sniff_document(content)
    if kind is None:
        raise UnsupportedAttachment(f"{filename} is not a PDF or a JPEG, PNG or HEIC photo.")
    digest = hashlib.sha256(content).hexdigest()
    existing = session.exec(select(RecordAttachment).where(
        RecordAttachment.record_id == record_id, RecordAttachment.sha256 == digest)).first()
    if existing is not None:
        return existing
    relative = f"attachments/{digest}{kind.extension}"
    target = settings.data_dir / relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    attachment = RecordAttachment(record_id=record_id, filename=filename, stored_path=relative,
                                  mime_type=kind.mime_type, size_bytes=len(content), sha256=digest)
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def attach_file(session: Session, record_id: int, source: Path) -> RecordAttachment:
    """Copy `source` into data/attachments (once per distinct content) and link it to the record. Idempotent."""
    return attach_bytes(session, record_id, source.read_bytes(), source.name)
