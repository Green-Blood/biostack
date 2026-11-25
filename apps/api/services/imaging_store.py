"""Where imaging studies live on disk: one folder per archive hash holding the ZIP and its keyframe PNGs."""
import json
import shutil
import uuid
from pathlib import Path

from sqlmodel import Session, select

from config import settings
from db.models import ImagingStudy


def imaging_root() -> Path:
    return settings.data_dir / "imaging"


def new_upload_path() -> Path:
    imaging_root().mkdir(parents=True, exist_ok=True)
    return imaging_root() / f"upload-{uuid.uuid4().hex}.part"


def study_folder(file_hash: str) -> Path:
    return imaging_root() / file_hash


def report_folder() -> Path:
    return imaging_root() / "reports"


def cached_report(file_hash: str) -> dict | None:
    """The draft already extracted from this report file, so the same file never goes to the AI twice."""
    path = report_folder() / f"{file_hash}.draft.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_report_and_draft(file_hash: str, content: bytes, draft_json: str) -> None:
    folder = report_folder()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / file_hash).write_bytes(content)
    (folder / f"{file_hash}.draft.json").write_text(draft_json, encoding="utf-8")


def zip_relpath(file_hash: str) -> str:
    return f"imaging/{file_hash}/study.zip"


def adopt_upload(upload: Path, file_hash: str) -> Path:
    """Move a finished upload into its hash folder and return the ZIP's path."""
    folder = study_folder(file_hash)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "study.zip"
    upload.replace(target)
    return target


def discard_folder(file_hash: str) -> None:
    shutil.rmtree(study_folder(file_hash), ignore_errors=True)


def relative_to_data(path: Path) -> str:
    return path.relative_to(settings.data_dir).as_posix()


def find_by_hash(session: Session, file_hash: str) -> ImagingStudy | None:
    return session.exec(select(ImagingStudy).where(ImagingStudy.file_hash == file_hash)).first()


def frame_file(study: ImagingStudy, index: int) -> Path | None:
    """The keyframe PNG for `index`, or None when it is out of range or would leave the data folder."""
    if not 0 <= index < len(study.keyframe_paths):
        return None
    root = settings.data_dir.resolve()
    path = (root / study.keyframe_paths[index]).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def delete_study(session: Session, study: ImagingStudy) -> None:
    file_hash = study.file_hash
    session.delete(study)
    session.commit()
    if file_hash:
        discard_folder(file_hash)
