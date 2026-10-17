"""Pipeline glue tested with a fake detector, so no YOLO or real video is needed."""

import numpy as np

from constructsafe.config import load_config
from constructsafe.detection import Detection
from constructsafe.pipeline import monitor_frames
from constructsafe.sources import Frame
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


def test_missed_detections_are_tolerated():
    xs = [150, 150, None, 150, None, None, 150, 150]
    config = load_config(enter_persistence_frames=2, exit_persistence_frames=3)
    results = list(monitor_frames(frames(len(xs)), ScriptedDetector(xs), [ZONE], config))
    assert sum(len(r.events) for r in results) == 1
    assert all(r.zones.active_zone_ids for r in results[1:])
