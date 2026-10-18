"""Scenario tests for the zone-entry state machine (PRD §13), using synthetic detections."""

import pytest

from constructsafe.detection import Detection
from constructsafe.events import (
    EVENT_ADDITIONAL_ENTRY,
    EVENT_ZONE_ENTRY,
    ZoneEventEngine,
    ZoneOccupancyMonitor,
)
from constructsafe.zones import DangerZone

FPS = 10.0


def run(monitor, counts):
    """Feed per-frame raw counts; return the list of updates."""
    return [monitor.update(i, i / FPS, c) for i, c in enumerate(counts)]


def events_of(updates):
    return [e for u in updates for e in u.events]


def make_monitor(enter=3, exit=5):
    return ZoneOccupancyMonitor("zone", enter_frames=enter, exit_frames=exit)


def test_worker_outside_zone_never_alerts():
    updates = run(make_monitor(), [0] * 30)
    assert events_of(updates) == []
    assert not any(u.active for u in updates)


def test_worker_entering_triggers_one_event_after_persistence():
    updates = run(make_monitor(enter=3), [0, 0, 1, 1, 1, 1, 1])
    events = events_of(updates)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EVENT_ZONE_ENTRY
    assert event.frame_index == 4  # third consecutive frame with the worker inside
    assert event.first_seen_seconds == pytest.approx(0.2)
    assert event.timestamp_seconds == pytest.approx(0.4)
    assert event.workers_in_zone == 1
    assert "human review" in event.description
    assert [u.active for u in updates] == [False, False, False, False, True, True, True]


def test_worker_staying_inside_does_not_repeat_events():
    updates = run(make_monitor(), [1] * 200)
    assert len(events_of(updates)) == 1


def test_worker_leaving_clears_warning_after_exit_persistence():
    counts = [1] * 5 + [0] * 6
    updates = run(make_monitor(enter=3, exit=5), counts)
    cleared = [i for i, u in enumerate(updates) if u.cleared]
    assert cleared == [9]  # fifth consecutive empty frame
    assert updates[8].active and not updates[9].active and not updates[10].active


def test_re_entry_after_clear_is_a_new_event():
    counts = [1] * 5 + [0] * 5 + [1] * 5
    events = events_of(run(make_monitor(enter=3, exit=5), counts))
    assert [e.event_type for e in events] == [EVENT_ZONE_ENTRY, EVENT_ZONE_ENTRY]


def test_single_frame_false_detection_is_ignored():
    events = events_of(run(make_monitor(enter=3), [0, 0, 1, 0, 0, 1, 1, 0, 0]))
    assert events == []


def test_flickering_detection_inside_zone_does_not_clear_or_duplicate():
    # worker inside, detector drops them every few frames (occlusion / missed detections)
    counts = [1, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1]
    updates = run(make_monitor(enter=3, exit=5), counts)
    assert len(events_of(updates)) == 1
    assert not any(u.cleared for u in updates)
    assert all(u.active for u in updates[2:])


def test_worker_leaving_the_frame_eventually_clears():
    # worker inside, then they leave the camera view: detections stop entirely
    updates = run(make_monitor(enter=3, exit=5), [1] * 4 + [0] * 20)
    assert sum(u.cleared for u in updates) == 1
    assert not updates[-1].active


def test_second_worker_entering_is_reported_as_additional_entry():
    counts = [1] * 4 + [2] * 4
    events = events_of(run(make_monitor(enter=3), counts))
    assert [e.event_type for e in events] == [EVENT_ZONE_ENTRY, EVENT_ADDITIONAL_ENTRY]
    assert events[1].workers_in_zone == 2
    assert events[1].workers_entered == 1


def test_two_workers_entering_together_is_one_event():
    events = events_of(run(make_monitor(enter=3), [0, 2, 2, 2, 2]))
    assert len(events) == 1
    assert events[0].workers_in_zone == 2 and events[0].workers_entered == 2


def test_rising_window_confirms_the_count_that_held():
    # count wobbles between 1 and 2 while rising: only 1 worker held for the full window
    events = events_of(run(make_monitor(enter=3), [2, 1, 2]))
    assert events[0].workers_in_zone == 1


def test_one_of_two_workers_leaving_keeps_warning_active():
    updates = run(make_monitor(enter=3, exit=5), [2] * 4 + [1] * 10)
    assert updates[-1].confirmed_count == 1
    assert updates[-1].active
    assert not any(u.cleared for u in updates)
    # no new event for someone leaving
    assert len(events_of(updates)) == 1


def test_persistence_of_one_reacts_immediately():
    updates = run(make_monitor(enter=1, exit=1), [0, 1, 0])
    assert [u.active for u in updates] == [False, True, False]
    assert len(events_of(updates)) == 1


def test_invalid_settings_and_counts():
    with pytest.raises(ValueError):
        ZoneOccupancyMonitor("z", enter_frames=0)
    with pytest.raises(ValueError):
        make_monitor().update(0, 0.0, -1)


# --- engine: zones + detections -------------------------------------------------

LEFT = DangerZone("left", "Left", ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)))
RIGHT = DangerZone("right", "Right", ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)))
W, H = 1000, 500


def person(cx, foot_y, w=40, h=120, conf=0.9):
    return Detection(cx - w / 2, foot_y - h, cx + w / 2, foot_y, "person", conf, 0)


def test_engine_uses_foot_point_and_handles_multiple_zones():
    engine = ZoneEventEngine([LEFT, RIGHT], enter_frames=2, exit_frames=2)
    left_worker = person(200, 400)
    # box straddles the boundary but the feet are in the right zone
    straddling = Detection(450, 100, 560, 400, "person", 0.8, 0)

    r0 = engine.update(0, 0.0, [left_worker, straddling], W, H)
    r1 = engine.update(1, 0.1, [left_worker, straddling], W, H)

    assert r0.events == []
    assert {e.zone_id for e in r1.events} == {"left", "right"}
    assert r1.workers_in_zones["left"] == (left_worker,)
    assert r1.workers_in_zones["right"] == (straddling,)
    assert r1.is_in_any_zone(left_worker)
    assert sorted(r1.active_zone_ids) == ["left", "right"]


def test_engine_with_no_detections_does_not_crash():
    engine = ZoneEventEngine([LEFT], enter_frames=2, exit_frames=2)
    for i in range(5):
        result = engine.update(i, i / FPS, [], W, H)
    assert result.events == []
    assert result.active_zone_ids == []


def test_engine_rejects_duplicate_zone_ids():
    with pytest.raises(ValueError):
        ZoneEventEngine([LEFT, LEFT], enter_frames=2, exit_frames=2)


def test_duplicate_boxes_no_longer_fake_an_additional_worker():
    """Regression for the false alarms seen on the Pexels 33769531 clip."""
    from constructsafe.detection import suppress_duplicates

    zone = DangerZone("z", "Z", ((0.25, 0.55), (0.8, 0.55), (0.8, 0.88), (0.25, 0.88)))
    engine = ZoneEventEngine([zone], enter_frames=3, exit_frames=5)
    one = Detection(430, 423, 488, 527, "person", 0.63, 0)
    dup = Detection(431, 424, 472, 526, "person", 0.38, 0)
    events = []
    for i in range(10):
        dets = [one, dup] if i >= 4 else [one]  # the duplicate appears after the worker entered
        dets = suppress_duplicates(dets, iou_threshold=0.55, containment_threshold=0.85)
        events += engine.update(i, i / 30, dets, 1280, 720).events
    assert [e.event_type for e in events] == [EVENT_ZONE_ENTRY]
