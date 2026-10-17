"""Pipeline glue tested with a fake detector, so no YOLO or real video is needed."""

import cv2
import numpy as np
import pytest

from constructsafe.config import load_config
from constructsafe.detection import Detection
from constructsafe.evidence import resolve_evidence_path
from constructsafe.pipeline import monitor_frames, process_video
from constructsafe.sources import Frame
from constructsafe.storage import STATUS_COMPLETED, STATUS_FAILED, Storage
from constructsafe.zones import DangerZone

W, H = 200, 100
ZONE = DangerZone("z", "Excavator", ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)))


class ScriptedDetector:
    """Returns one worker whose foot x position is scripted per frame (None = no detection)."""

    def __init__(self, xs):
        self.xs = iter(xs)

    def detect_people(self, image):
        x = next(self.xs)
        if x is None:
            return []
        return [Detection(x - 5, 40, x + 5, 90, "person", 0.9, 0)]


def frames(n):
    for i in range(n):
        yield Frame(index=i, timestamp_seconds=i / 10, image=np.zeros((H, W, 3), dtype=np.uint8))


def test_walk_in_and_out_produces_one_event_and_a_banner_only_while_active():
    # outside x2, inside x4, outside x4
    xs = [50, 50, 150, 150, 150, 150, 50, 50, 50, 50]
    config = load_config(enter_persistence_frames=2, exit_persistence_frames=2)

    results = list(monitor_frames(frames(len(xs)), ScriptedDetector(xs), [ZONE], config))

    events = [e for r in results for e in r.events]
    assert len(events) == 1
    assert events[0].frame_index == 3
    active = [bool(r.zones.active_zone_ids) for r in results]
    assert active == [False, False, False, True, True, True, True, False, False, False]
    # the red banner is drawn at the top only while active
    banner_red = [r.annotated[2, W // 2, 2] > 200 and r.annotated[2, W // 2, 1] < 50 for r in results]
    assert banner_red == active
    # the input frames are never drawn on
    assert all(r.frame.image.sum() == 0 for r in results)


@pytest.fixture
def video_and_config(tmp_path):
    path = tmp_path / "walk.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (W, H))
    for _ in range(10):
        writer.write(np.zeros((H, W, 3), dtype=np.uint8))
    writer.release()
    config = load_config(
        data_dir=tmp_path / "data", enter_persistence_frames=2, exit_persistence_frames=2, max_frame_width=0
    )
    return path, config


def test_process_video_logs_events_with_evidence(video_and_config):
    path, config = video_and_config
    storage = Storage(config.database_path)
    xs = [50, 50, 150, 150, 150, 50, 50, 50, 150, 150]  # two separate entries

    summary = process_video(path, config, storage, zones=[ZONE], detector=ScriptedDetector(xs))

    assert summary.status == STATUS_COMPLETED
    assert summary.frames_processed == 10
    run = storage.get_run(summary.run_id)
    assert run.status == STATUS_COMPLETED and run.frames_processed == 10
    events = storage.list_events(run_id=summary.run_id)
    assert [e.frame_index for e in events] == [3, 9]
    for event in events:
        image = cv2.imread(str(resolve_evidence_path(config.evidence_dir, event.evidence_path)))
        assert image is not None and image.shape == (H, W, 3)
    assert summary.output_path.exists()


def test_process_video_uses_stored_zones(video_and_config):
    path, config = video_and_config
    storage = Storage(config.database_path)
    storage.save_zone(DangerZone("z", "Stored", ZONE.polygon, source_name=path.name))

    summary = process_video(path, config, storage, detector=ScriptedDetector([150] * 10))

    assert summary.status == STATUS_COMPLETED
    assert len(summary.event_ids) == 1


def test_process_video_fails_cleanly_without_zones(video_and_config):
    path, config = video_and_config
    storage = Storage(config.database_path)
    summary = process_video(path, config, storage, detector=ScriptedDetector([]))
    assert summary.status == STATUS_FAILED
    assert "No danger zone" in summary.error_message
    assert storage.get_run(summary.run_id).status == STATUS_FAILED


def test_process_video_fails_cleanly_on_invalid_file(tmp_path, video_and_config):
    _, config = video_and_config
    storage = Storage(config.database_path)
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")

    summary = process_video(bad, config, storage, zones=[ZONE], detector=ScriptedDetector([]))

    assert summary.status == STATUS_FAILED
    run = storage.get_run(summary.run_id)
    assert run.status == STATUS_FAILED and "broken.mp4" in run.error_message


def test_process_video_records_detector_crash_and_keeps_earlier_events(video_and_config):
    path, config = video_and_config
    storage = Storage(config.database_path)
    xs = [150, 150, 150, 150, 150]  # then the iterator runs out -> StopIteration inside the detector

    class Crashing(ScriptedDetector):
        def detect_people(self, image):
            try:
                return super().detect_people(image)
            except StopIteration:
                raise RuntimeError("model exploded") from None

    summary = process_video(path, config, storage, zones=[ZONE], detector=Crashing(xs))

    assert summary.status == STATUS_FAILED
    assert "model exploded" in summary.error_message and "after 5 frames" in summary.error_message
    assert len(storage.list_events(run_id=summary.run_id)) == 1  # the event before the crash is kept


def test_evidence_failure_still_logs_the_event(video_and_config, monkeypatch):
    path, config = video_and_config
    storage = Storage(config.database_path)

    def broken_save(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("constructsafe.pipeline.save_evidence", broken_save)
    summary = process_video(path, config, storage, zones=[ZONE], detector=ScriptedDetector([150] * 10))

    assert summary.status == STATUS_COMPLETED
    events = storage.list_events(run_id=summary.run_id)
    assert len(events) == 1 and events[0].evidence_path is None


def test_missed_detections_are_tolerated():
    xs = [150, 150, None, 150, None, None, 150, 150]
    config = load_config(enter_persistence_frames=2, exit_persistence_frames=3)
    results = list(monitor_frames(frames(len(xs)), ScriptedDetector(xs), [ZONE], config))
    assert sum(len(r.events) for r in results) == 1
    assert all(r.zones.active_zone_ids for r in results[1:])
