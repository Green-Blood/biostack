"""Turn a ZIP of DICOM files into a handful of viewable PNG keyframes.

The archive is read in place (never unpacked to disk), so member names cannot write outside any folder; names
that try to are still rejected so a hostile archive is reported instead of silently half-read. Only pixel data,
never patient fields, is used for the frames, and only study-level technical tags are kept as metadata.
"""
import datetime as dt
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image
from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError

MAX_FRAME_SIDE = 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 8 * 1024**3
STUDY_TYPES = {"CT": "CT", "MR": "MRI", "US": "Ultrasound", "CR": "X-ray", "DX": "X-ray", "MG": "Mammography",
               "PT": "PET", "NM": "Nuclear medicine"}


class DicomArchiveError(Exception):
    """The archive cannot be turned into keyframes; the message says why and what to do."""


class InvalidArchiveError(DicomArchiveError):
    """The file is not a readable ZIP archive."""


class UnsafeArchiveError(DicomArchiveError):
    """The archive contains paths that escape its folder, or is implausibly large."""


class NoImagesError(DicomArchiveError):
    """The archive holds no DICOM image that could be decoded."""


@dataclass(frozen=True)
class StudyMetadata:
    study_date: dt.date | None
    modality: str
    body_part: str
    study_description: str
    series_description: str
    slice_count: int

    @property
    def study_type(self) -> str:
        return STUDY_TYPES.get(self.modality, self.modality)


@dataclass(frozen=True)
class KeyframeResult:
    metadata: StudyMetadata
    frames: list[Path]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Slice:
    member: str
    header: Dataset

    @property
    def sort_key(self) -> tuple[float, float, str]:
        return (_number_or_last(self.header.get("InstanceNumber")), self._depth(), self.member)

    def _depth(self) -> float:
        """The slice's position along the scan axis; slices with a malformed position sort last."""
        position = self.header.get("ImagePositionPatient")
        return _number_or_last(position[2]) if position is not None and len(position) == 3 else float("inf")


def _number_or_last(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("inf")


def extract_keyframes(zip_path: Path, out_dir: Path, count: int = 5) -> KeyframeResult:
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise InvalidArchiveError("This file is not a valid ZIP archive. Upload a ZIP of DICOM files.") from exc
    with archive:
        _check_members(archive)
        slices, unreadable = _image_slices(archive)
        series = _largest_series(slices)
        if not series:
            raise NoImagesError("This archive has no DICOM images. Upload a ZIP made from a scan export.")
        out_dir.mkdir(parents=True, exist_ok=True)
        frames, warnings = _render_keyframes(archive, series, out_dir, count)
    if unreadable:
        warnings.append(f"{unreadable} damaged file(s) in the archive could not be read and were skipped.")
    if not frames:
        raise NoImagesError("The images in this archive use a compressed format this app cannot decode yet.")
    return KeyframeResult(_metadata(series), frames, warnings)


def _check_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
        raise UnsafeArchiveError("This archive is too large to process safely. Upload a smaller export.")
    for info in infos:
        if info.flag_bits & 0x1:
            raise DicomArchiveError("This archive is password-protected. Remove the password, then upload it again.")
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if name.is_absolute() or ".." in name.parts:
            raise UnsafeArchiveError("This archive contains unsafe file paths, so it was not opened.")


def _image_slices(archive: zipfile.ZipFile) -> tuple[list[_Slice], int]:
    """The DICOM image slices, plus how many archive members were damaged and could not be read."""
    slices, unreadable = [], 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        try:
            with archive.open(info) as stream:
                header = dcmread(stream, stop_before_pixels=True)
        except (InvalidDicomError, EOFError, ValueError, NotImplementedError):
            continue  # not a DICOM file (readme, viewer executable, ...)
        except (zlib.error, zipfile.BadZipFile, RuntimeError, OSError):
            unreadable += 1
            continue
        if "Rows" in header and "Columns" in header:
            slices.append(_Slice(info.filename, header))
    return slices, unreadable


def _largest_series(slices: list[_Slice]) -> list[_Slice]:
    by_series: dict[str, list[_Slice]] = {}
    for item in slices:
        by_series.setdefault(str(item.header.get("SeriesInstanceUID", "")), []).append(item)
    if not by_series:
        return []
    return sorted(max(by_series.values(), key=len), key=lambda s: s.sort_key)


def _evenly_spaced(total: int, count: int) -> list[int]:
    """Centered picks, so the first and last (often empty) slices of a stack are avoided."""
    if total <= count:
        return list(range(total))
    return [int((i + 0.5) * total / count) for i in range(count)]


def _render_keyframes(archive: zipfile.ZipFile, series: list[_Slice], out_dir: Path,
                      count: int) -> tuple[list[Path], list[str]]:
    frames: list[Path] = []
    warnings: list[str] = []
    for number, index in enumerate(_evenly_spaced(len(series), count), start=1):
        chosen = series[index]
        try:
            with archive.open(chosen.member) as stream:
                pixels = _to_gray_or_rgb(dcmread(stream))
        except Exception:  # noqa: BLE001 - pydicom decoders raise many unrelated types for unsupported encodings
            warnings.append(f"Slice {chosen.header.get('InstanceNumber', index + 1)} could not be decoded and was skipped.")
            continue
        path = out_dir / f"frame_{number:02d}.png"
        _save_png(pixels, path)
        frames.append(path)
    return frames, warnings


def _to_gray_or_rgb(dataset: Dataset) -> np.ndarray:
    pixels = dataset.pixel_array
    if int(dataset.get("NumberOfFrames", 1)) > 1:
        pixels = pixels[len(pixels) // 2]
    if pixels.ndim == 3:  # colour (e.g. ultrasound): already display-ready
        return pixels.astype(np.uint8)
    values = pixels.astype(np.float64) * float(dataset.get("RescaleSlope", 1)) + float(dataset.get("RescaleIntercept", 0))
    low, high = _window(dataset, values)
    scaled = np.clip((values - low) / max(high - low, 1e-9), 0, 1) * 255
    if dataset.get("PhotometricInterpretation") == "MONOCHROME1":
        scaled = 255 - scaled
    return scaled.round().astype(np.uint8)


def _window(dataset: Dataset, values: np.ndarray) -> tuple[float, float]:
    center, width = dataset.get("WindowCenter"), dataset.get("WindowWidth")
    if center is not None and width is not None:
        center, width = float(np.atleast_1d(center)[0]), float(np.atleast_1d(width)[0])
        return center - width / 2, center + width / 2
    low, high = np.percentile(values, [1, 99])
    return float(low), float(high)


def _save_png(pixels: np.ndarray, path: Path) -> None:
    image = Image.fromarray(pixels)
    image.thumbnail((MAX_FRAME_SIDE, MAX_FRAME_SIDE))
    image.save(path, format="PNG")


def _metadata(series: list[_Slice]) -> StudyMetadata:
    header = series[0].header
    return StudyMetadata(
        study_date=_parse_date(str(header.get("StudyDate", ""))),
        modality=str(header.get("Modality", "")),
        body_part=str(header.get("BodyPartExamined", "")),
        study_description=str(header.get("StudyDescription", "")),
        series_description=str(header.get("SeriesDescription", "")),
        slice_count=len(series),
    )


def _parse_date(raw: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None
