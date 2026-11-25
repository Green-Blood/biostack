import datetime as dt
import random

import numpy as np
import pytest
from PIL import Image

from services.dicom_processor import (
    DicomArchiveError, InvalidArchiveError, NoImagesError, UnsafeArchiveError, extract_keyframes,
)
from tests.dicom_factory import (
    JPEGLSLossless, corrupt_member, dicom_bytes, dicom_bytes_with_position, make_zip, mark_encrypted,
    no_image_dicom_bytes, series_members,
)


def _gray(path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"))


def test_picks_five_evenly_spaced_slices_in_order_regardless_of_zip_order(tmp_path):
    members = list(series_members(12).items())
    random.Random(3).shuffle(members)
    result = extract_keyframes(make_zip(tmp_path / "s.zip", dict(members)), tmp_path / "out")
    assert len(result.frames) == 5 and result.metadata.slice_count == 12
    levels = [int(_gray(p).mean()) for p in result.frames]
    assert levels == sorted(levels) and len(set(levels)) == 5
    # slices 2, 4, 7, 9 and 11 (1-based) have stored values 924, 984, 1074, 1134, 1194; window 40/400 starts at 864
    expected = [round((v - 864) / 400 * 255) for v in (924, 984, 1074, 1134, 1194)]
    assert levels == pytest.approx(expected, abs=2)
    assert all(p.parent == tmp_path / "out" and p.suffix == ".png" for p in result.frames)


def test_fewer_slices_than_requested_returns_all(tmp_path):
    result = extract_keyframes(make_zip(tmp_path / "s.zip", series_members(3)), tmp_path / "out")
    assert len(result.frames) == 3


def test_uses_the_largest_series(tmp_path):
    members = {**series_members(3, series_uid="1.9", prefix="small", series_description="Scout"),
               **series_members(8, series_uid="1.8", prefix="big", series_description="Axial soft tissue")}
    result = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out")
    assert result.metadata.slice_count == 8 and result.metadata.series_description == "Axial soft tissue"


def test_reads_study_metadata_from_tags_and_no_patient_data(tmp_path):
    result = extract_keyframes(make_zip(tmp_path / "s.zip", series_members(2)), tmp_path / "out")
    meta = result.metadata
    assert (meta.modality, meta.body_part, meta.study_date) == ("CT", "CHEST", dt.date(2024, 3, 15))
    assert "Synthetic" not in repr(result)


def test_metadata_is_empty_when_tags_are_missing(tmp_path):
    members = {"a.dcm": dicom_bytes(study_date=None, body_part=None, modality="")}
    meta = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out").metadata
    assert meta.study_date is None and meta.body_part == ""


def test_applies_rescale_and_window(tmp_path):
    members = {"a.dcm": dicom_bytes(fill=1024 + 40), "b.dcm": dicom_bytes(instance=2, fill=0)}
    frames = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out").frames
    assert _gray(frames[0]).mean() == pytest.approx(128, abs=2)   # 40 HU is the window center
    assert _gray(frames[1]).max() == 0                            # air is far below the window


def test_percentile_window_when_no_window_tags(tmp_path):
    result = extract_keyframes(make_zip(tmp_path / "s.zip", {"a.dcm": dicom_bytes(window=None)}), tmp_path / "out")
    pixels = _gray(result.frames[0])
    assert pixels.min() <= 5 and pixels.max() >= 250


def test_monochrome1_is_inverted(tmp_path):
    bright = {"a.dcm": dicom_bytes(fill=1024 + 200, photometric="MONOCHROME1")}
    frame = extract_keyframes(make_zip(tmp_path / "s.zip", bright), tmp_path / "out").frames[0]
    assert _gray(frame).mean() < 60


def test_large_images_are_scaled_to_at_most_1024_pixels(tmp_path):
    members = {"a.dcm": dicom_bytes(rows=1536, cols=2048, fill=1100)}
    frame = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out").frames[0]
    assert Image.open(frame).size == (1024, 768)


def test_multiframe_object_uses_its_middle_frame(tmp_path):
    members = {"cine.dcm": dicom_bytes(frames=3, fill=1100)}
    assert len(extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out").frames) == 1


def test_skips_non_image_files_and_reports_undecodable_slices(tmp_path):
    members = {**series_members(6), "notes.txt": b"hello", "report.dcm": no_image_dicom_bytes(),
               "S1/IM9999.dcm": dicom_bytes(instance=99, transfer_syntax=JPEGLSLossless)}
    result = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out")
    assert len(result.frames) >= 4
    assert any("could not be decoded" in w for w in result.warnings)


def test_only_undecodable_images_is_an_error_naming_the_cause(tmp_path):
    members = {"a.dcm": dicom_bytes(transfer_syntax=JPEGLSLossless)}
    with pytest.raises(NoImagesError, match="compressed"):
        extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out")


@pytest.mark.parametrize("evil", ["../evil.dcm", "/etc/evil.dcm", "a/../../evil.dcm"])
def test_zip_slip_member_names_are_rejected(tmp_path, evil):
    zip_path = make_zip(tmp_path / "s.zip", {evil: dicom_bytes(), "ok.dcm": dicom_bytes()})
    with pytest.raises(UnsafeArchiveError):
        extract_keyframes(zip_path, tmp_path / "out")
    assert not (tmp_path / "evil.dcm").exists()


def test_not_a_zip_and_empty_zip_are_rejected(tmp_path):
    (tmp_path / "bad.zip").write_bytes(b"this is not a zip")
    with pytest.raises(InvalidArchiveError):
        extract_keyframes(tmp_path / "bad.zip", tmp_path / "out")
    with pytest.raises(NoImagesError):
        extract_keyframes(make_zip(tmp_path / "empty.zip", {}), tmp_path / "out2")
    assert issubclass(NoImagesError, DicomArchiveError)


def test_a_corrupt_member_is_skipped_with_a_warning(tmp_path):
    members = series_members(6)
    zip_path = corrupt_member(make_zip(tmp_path / "s.zip", members), "S1/IM0003.dcm")
    result = extract_keyframes(zip_path, tmp_path / "out")
    assert len(result.frames) == 5 and result.metadata.slice_count == 5
    assert any("could not be read" in w for w in result.warnings)


def test_an_archive_where_every_member_is_corrupt_is_a_clear_error(tmp_path):
    zip_path = corrupt_member(make_zip(tmp_path / "s.zip", {"S1/IM0001.dcm": dicom_bytes()}), "S1/IM0001.dcm")
    with pytest.raises(DicomArchiveError, match="no DICOM images"):
        extract_keyframes(zip_path, tmp_path / "out")


def test_a_password_protected_archive_is_a_clear_error(tmp_path):
    zip_path = mark_encrypted(make_zip(tmp_path / "s.zip", series_members(3)))
    with pytest.raises(DicomArchiveError, match="password"):
        extract_keyframes(zip_path, tmp_path / "out")


def test_a_wrong_number_of_position_values_does_not_stop_the_archive(tmp_path):
    members = series_members(4)
    members["S1/IM0002.dcm"] = dicom_bytes_with_position([0.0, 1.0], instance=2, fill=900)
    result = extract_keyframes(make_zip(tmp_path / "s.zip", members), tmp_path / "out")
    assert result.metadata.slice_count == 4 and len(result.frames) == 4
