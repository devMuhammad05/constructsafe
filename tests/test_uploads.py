import cv2
import numpy as np
import pytest

from constructsafe.config import load_config
from constructsafe.sources import VideoValidationError
from constructsafe.storage import STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING, Storage
from constructsafe.uploads import list_videos, resolve_video, save_upload, upload_target


@pytest.fixture
def config(tmp_path):
    return load_config(data_dir=tmp_path / "data")


def video_bytes(tmp_path):
    path = tmp_path / "src.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (32, 24))
    for _ in range(5):
        writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def test_save_valid_upload(tmp_path, config):
    info = save_upload(video_bytes(tmp_path), "Site Cam (1).AVI", config)
    assert info.path == config.videos_dir / "Site_Cam_1.avi"
    assert info.frame_count == 5
    assert list_videos(config) == [info.path]
    assert not list(config.videos_dir.glob("*.uploading*"))


def test_rejects_wrong_type_before_writing(config):
    with pytest.raises(VideoValidationError, match="Unsupported file type"):
        save_upload(b"#!/bin/sh", "payload.sh", config)
    assert not config.videos_dir.exists()


def test_rejects_and_removes_unreadable_video(config):
    with pytest.raises(VideoValidationError, match="could not be read"):
        save_upload(b"definitely not a video", "clip.mp4", config)
    assert list_videos(config) == []
    assert not any(config.videos_dir.iterdir())


def test_rejects_empty_upload(config):
    with pytest.raises(VideoValidationError, match="empty"):
        save_upload(b"", "clip.mp4", config)


def test_upload_name_cannot_escape_videos_dir(config):
    target = upload_target("../../../evil.mp4", config)
    assert target.parent == config.videos_dir


def test_resolve_video_rejects_traversal(config):
    config.videos_dir.mkdir(parents=True)
    assert resolve_video(config, "a.mp4") == (config.videos_dir / "a.mp4").resolve()
    for bad in ("../a.mp4", "sub/a.mp4", r"..\a.mp4", r"sub\a.mp4"):
        with pytest.raises(VideoValidationError):
            resolve_video(config, bad)


def test_fail_interrupted_runs(config):
    storage = Storage(config.database_path)
    stuck = storage.create_run("a.mp4")
    done = storage.create_run("b.mp4")
    storage.update_run(stuck, status=STATUS_PROCESSING)
    storage.update_run(done, status=STATUS_COMPLETED)

    assert storage.fail_interrupted_runs() == 1

    assert storage.get_run(stuck).status == STATUS_FAILED
    assert "interrupted" in storage.get_run(stuck).error_message
    assert storage.get_run(done).status == STATUS_COMPLETED
