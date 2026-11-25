"""Builds tiny synthetic DICOM files and ZIPs for tests. Nothing here resembles a real scan."""
import io
import zipfile
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, JPEGLSLossless, generate_uid

STUDY_UID = generate_uid()


def dicom_bytes(
    *, series_uid: str = "1.2.3.1", instance: int = 1, fill: int | None = None, rows: int = 64, cols: int = 64,
    window: tuple[int, int] | None = (40, 400), intercept: int = -1024, photometric: str = "MONOCHROME2",
    transfer_syntax: str = ExplicitVRLittleEndian, study_date: str | None = "20240315", modality: str = "CT",
    body_part: str | None = "CHEST", series_description: str = "Axial", frames: int = 1,
) -> bytes:
    """One CT-like slice. `fill` makes the whole slice one stored value; otherwise a gradient is drawn."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = transfer_syntax
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID, ds.SeriesInstanceUID = STUDY_UID, series_uid
    ds.Modality, ds.SeriesDescription, ds.InstanceNumber = modality, series_description, instance
    if study_date:
        ds.StudyDate = study_date
    if body_part:
        ds.BodyPartExamined = body_part
    ds.PatientName, ds.PatientID = "Synthetic^Test", "SYNTH-0"
    ds.Rows, ds.Columns, ds.SamplesPerPixel = rows, cols, 1
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation = 15, 0
    ds.RescaleSlope, ds.RescaleIntercept = 1, intercept
    if window:
        ds.WindowCenter, ds.WindowWidth = window
    if frames > 1:
        ds.NumberOfFrames = frames
    ds.ImagePositionPatient = [0, 0, float(instance)]
    if transfer_syntax == JPEGLSLossless:
        ds.PixelData = encapsulate([b"not really jpeg-ls"])
        ds["PixelData"].is_undefined_length = True
    else:
        shape = (frames, rows, cols) if frames > 1 else (rows, cols)
        pixels = np.full(shape, fill, dtype=np.uint16) if fill is not None else \
            np.broadcast_to(np.linspace(0, 2000, cols, dtype=np.uint16), shape).copy()
        ds.PixelData = pixels.tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()


def no_image_dicom_bytes() -> bytes:
    """A DICOM object with no pixel data, such as a structured report."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.11"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID, ds.Modality = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID, "SR"
    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()


def make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def series_members(count: int, *, series_uid: str = "1.2.3.1", prefix: str = "S1", **kwargs) -> dict[str, bytes]:
    """`count` slices whose stored value rises with the slice number: slice k is filled with 864 + 30*k (inside the default window)."""
    return {f"{prefix}/IM{k:04d}.dcm": dicom_bytes(series_uid=series_uid, instance=k, fill=864 + 30 * k, **kwargs)
            for k in range(1, count + 1)}


def corrupt_member(path: Path, member: str) -> Path:
    """Overwrite the start of a member's deflate stream so reading it raises a decompression error."""
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
        data_start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    raw = bytearray(path.read_bytes())
    raw[data_start:data_start + 8] = b"\xff" * 8
    path.write_bytes(bytes(raw))
    return path


def mark_encrypted(path: Path) -> Path:
    """Set the 'encrypted' flag on every member's central directory entry, as a password-protected ZIP does."""
    raw = bytearray(path.read_bytes())
    position = raw.find(b"PK\x01\x02")
    while position != -1:
        raw[position + 8] |= 0x1
        position = raw.find(b"PK\x01\x02", position + 4)
    path.write_bytes(bytes(raw))
    return path


def dicom_bytes_with_position(values: list[float], **kwargs) -> bytes:
    """A slice whose ImagePositionPatient carries `values`, even a wrong number of them."""
    from pydicom import dcmread

    dataset = dcmread(io.BytesIO(dicom_bytes(**kwargs)))
    dataset.ImagePositionPatient = values
    buffer = io.BytesIO()
    dataset.save_as(buffer)
    return buffer.getvalue()
