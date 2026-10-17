import json

import cv2
import numpy as np
import pytest

from constructsafe.evaluation import (
    LabelError,
    LabelledEntry,
    PrecisionRecall,
    PredictedEvent,
    evaluate_events,
    iou,
    load_detection_labels,
    load_event_labels,
    match_frame,
)
from constructsafe.sources import read_frame

# --- metrics -------------------------------------------------------------------


def test_precision_recall_and_empty_cases():
    pr = PrecisionRecall(3, 1, 2)
    assert pr.precision == pytest.approx(0.75)
    assert pr.recall == pytest.approx(0.6)
    assert pr.f1 == pytest.approx(2 * 0.75 * 0.6 / 1.35)
    empty = PrecisionRecall(0, 0, 0)
    assert empty.precision is None and empty.recall is None and empty.f1 is None
    assert (pr + PrecisionRecall(1, 1, 1)).as_dict()["true_positives"] == 4


# --- events --------------------------------------------------------------------


def entries(*times, zone="z"):
    return [LabelledEntry(zone, t) for t in times]


def events(*times, zone="z"):
    return [PredictedEvent(zone, t) for t in times]


def test_perfect_match_with_latency():
    result = evaluate_events(entries(5.0, 20.0), events(5.2, 20.5))
    assert result.counts == PrecisionRecall(2, 0, 0)
    assert result.latencies == pytest.approx([0.2, 0.5])
    assert result.latency_summary()["max"] == pytest.approx(0.5)


def test_missed_entry_and_false_alarm():
    result = evaluate_events(entries(5.0, 20.0), events(5.1, 40.0))
    assert result.counts == PrecisionRecall(1, 1, 1)
    assert [m.enter_seconds for m in result.missed] == [20.0]
    assert [f.timestamp_seconds for f in result.false_alarms] == [40.0]


def test_late_event_beyond_max_latency_does_not_count():
    result = evaluate_events(entries(5.0), events(7.5), max_latency=2.0)
    assert result.counts == PrecisionRecall(0, 1, 1)


def test_early_tolerance():
    assert evaluate_events(entries(5.0), events(4.6), early_tolerance=0.5).counts.true_positives == 1
    assert evaluate_events(entries(5.0), events(4.4), early_tolerance=0.5).counts.true_positives == 0


def test_matching_is_one_to_one():
    # two entries close together but only one event: one is missed
    result = evaluate_events(entries(5.0, 5.5), events(5.6))
    assert result.counts == PrecisionRecall(1, 0, 1)
    # one entry, two events (a duplicate alert): one false alarm
    result = evaluate_events(entries(5.0), events(5.2, 5.4))
    assert result.counts == PrecisionRecall(1, 1, 0)


def test_zones_must_match():
    result = evaluate_events(entries(5.0, zone="a"), events(5.2, zone="b"))
    assert result.counts == PrecisionRecall(0, 1, 1)


def test_no_labels_no_events():
    result = evaluate_events([], [])
    assert result.counts == PrecisionRecall(0, 0, 0)
    assert result.latency_summary()["mean"] is None


def test_report_is_json_serialisable():
    result = evaluate_events(entries(5.0), events(5.2, 9.0))
    json.dumps(result.as_dict())


def test_load_event_labels(tmp_path):
    path = tmp_path / "clip.events.json"
    path.write_text(json.dumps({
        "source_name": "clip.mp4",
        "zones": [{"zone_id": "exc", "name": "Excavator", "polygon": [[0, 0], [1, 0], [1, 1]]}],
        "entries": [{"zone_id": "exc", "enter_seconds": 3.5, "note": "from left"}],
        "labelled_by": "MY",
    }))
    labels = load_event_labels(path)
    assert labels.zones[0].source_name == "clip.mp4"
    assert labels.entries == (LabelledEntry("exc", 3.5, "from left"),)


def test_load_event_labels_rejects_unknown_zone(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "source_name": "clip.mp4",
        "zones": [{"zone_id": "exc", "polygon": [[0, 0], [1, 0], [1, 1]]}],
        "entries": [{"zone_id": "typo", "enter_seconds": 1}],
    }))
    with pytest.raises(LabelError, match="typo"):
        load_event_labels(path)


# --- detection -----------------------------------------------------------------


def test_iou():
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == pytest.approx(1.0)
    assert iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0
    assert iou((0, 0, 2, 1), (1, 0, 3, 1)) == pytest.approx(1 / 3)


def test_match_frame_counts():
    labelled = [(0.1, 0.1, 0.2, 0.4), (0.5, 0.5, 0.6, 0.9)]
    predicted = [
        ((0.1, 0.1, 0.2, 0.41), 0.9),  # TP
        ((0.11, 0.1, 0.21, 0.4), 0.8),  # duplicate of the same person -> FP
        ((0.8, 0.1, 0.9, 0.3), 0.7),  # nothing there -> FP
    ]
    assert match_frame(predicted, labelled) == PrecisionRecall(1, 2, 1)


def test_match_frame_prefers_higher_confidence():
    labelled = [(0.0, 0.0, 0.2, 0.2)]
    predicted = [((0.0, 0.0, 0.2, 0.19), 0.4), ((0.0, 0.0, 0.2, 0.2), 0.9)]
    assert match_frame(predicted, labelled) == PrecisionRecall(1, 1, 0)


def test_match_frame_with_no_people():
    assert match_frame([], []) == PrecisionRecall(0, 0, 0)
    assert match_frame([((0, 0, 0.1, 0.1), 0.5)], []) == PrecisionRecall(0, 1, 0)


def test_load_detection_labels_validates_boxes(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"source_name": "c.mp4", "frames": [{"frame_index": 3, "people": [[0.1, 0.2, 0.3, 0.6]]}]}))
    assert load_detection_labels(good).frames[0].people == ((0.1, 0.2, 0.3, 0.6),)

    pixels = tmp_path / "pixels.json"
    pixels.write_text(json.dumps({"source_name": "c.mp4", "frames": [{"frame_index": 3, "people": [[10, 20, 30, 60]]}]}))
    with pytest.raises(LabelError, match="normalised"):
        load_detection_labels(pixels)


def test_read_frame_by_index(tmp_path):
    path = tmp_path / "v.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (32, 24))
    for i in range(10):
        writer.write(np.full((24, 32, 3), i * 20, dtype=np.uint8))
    writer.release()
    frame = read_frame(path, 6)
    assert frame.index == 6 and frame.timestamp_seconds == pytest.approx(0.6)
    assert frame.image.mean() == pytest.approx(120, abs=8)
