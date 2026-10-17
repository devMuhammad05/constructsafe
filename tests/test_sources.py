import cv2
import numpy as np
import pytest

from constructsafe.sources import (
    VideoFileSource,
    VideoValidationError,
    resize_to_max_width,
    validate_video_file,
)

EXTS = (".mp4", ".avi")


@pytest.fixture
def synthetic_video(tmp_path):
    """A 20-frame, 10 fps video where each frame's brightness encodes its index."""
    path = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    for i in range(20):
        writer.write(np.full((48, 64, 3), i * 10, dtype=np.uint8))
    writer.release()
    return path


def test_validate_reads_metadata(synthetic_video):
    info = validate_video_file(synthetic_video, EXTS)
    assert (info.width, info.height) == (64, 48)
    assert info.fps == pytest.approx(10.0)
    assert info.frame_count == 20
    assert info.duration_seconds == pytest.approx(2.0)


def test_validate_rejects_missing_file(tmp_path):
    with pytest.raises(VideoValidationError, match="not found"):
        validate_video_file(tmp_path / "nope.mp4", EXTS)


def test_validate_rejects_wrong_extension(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(VideoValidationError, match="Unsupported file type"):
        validate_video_file(bad, EXTS)


def test_validate_rejects_corrupt_video(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"this is not a video")
    with pytest.raises(VideoValidationError):
        validate_video_file(bad, EXTS)


def test_source_yields_all_frames_with_timestamps(synthetic_video):
    frames = list(VideoFileSource(synthetic_video, allowed_extensions=EXTS))
    assert [f.index for f in frames] == list(range(20))
    assert frames[5].timestamp_seconds == pytest.approx(0.5)


def test_source_applies_frame_stride(synthetic_video):
    frames = list(VideoFileSource(synthetic_video, frame_stride=3, allowed_extensions=EXTS))
    assert [f.index for f in frames] == [0, 3, 6, 9, 12, 15, 18]
    # brightness encodes the original index, so the right frames were decoded
    assert frames[2].image.mean() == pytest.approx(60, abs=6)


def test_source_rejects_bad_stride(synthetic_video):
    with pytest.raises(ValueError):
        VideoFileSource(synthetic_video, frame_stride=0, allowed_extensions=EXTS)


def test_resize_only_downscales():
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    assert resize_to_max_width(image, 100).shape == (50, 100, 3)
    assert resize_to_max_width(image, 400) is image
    assert resize_to_max_width(image, 0) is image
