import cv2
import numpy as np
import pytest

from constructsafe.events import EVENT_ZONE_ENTRY, HazardEvent
from constructsafe.evidence import (
    EvidencePathError,
    evidence_filename,
    resolve_evidence_path,
    safe_name,
    save_evidence,
)

EVENT = HazardEvent("excavator", EVENT_ZONE_ENTRY, 42, 4.2, 4.0, 1, 1)


def test_safe_name_strips_path_and_odd_characters():
    assert safe_name("../../etc/passwd") == "etc_passwd"
    assert safe_name("site video (1).mp4") == "site_video_1_.mp4"
    assert safe_name("...") == "unnamed"
    assert len(safe_name("a" * 500)) == 60


def test_filename_cannot_contain_separators():
    name = evidence_filename(3, "..\\..\\evil/../clip.mp4", HazardEvent("../z", EVENT_ZONE_ENTRY, 1, 0.1, 0.0, 1, 1))
    assert "/" not in name and "\\" not in name
    assert name.startswith("run00003_") and name.endswith(".jpg")


def test_resolve_rejects_traversal(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    assert resolve_evidence_path(root, "ok.jpg") == (root / "ok.jpg").resolve()
    for bad in ("../secret.jpg", "sub/../../secret.jpg", str(tmp_path / "abs.jpg")):
        with pytest.raises(EvidencePathError):
            resolve_evidence_path(root, bad)


def test_save_evidence_writes_a_readable_jpeg(tmp_path):
    image = np.full((60, 80, 3), 127, dtype=np.uint8)
    relative = save_evidence(tmp_path / "evidence", image, run_id=1, source_name="site.mp4", event=EVENT)

    path = resolve_evidence_path(tmp_path / "evidence", relative)
    loaded = cv2.imread(str(path))
    assert loaded.shape == image.shape
    assert "f0000042" in relative and "excavator" in relative
