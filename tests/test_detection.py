import numpy as np
import pytest

from constructsafe.annotate import draw_detections
from constructsafe.detection import PERSON_CLASS_ID, Detection, detections_from_arrays

NAMES = {0: "person", 2: "car", 7: "truck"}


def test_foot_point_is_bottom_centre():
    det = Detection(10, 20, 30, 100, label="person", confidence=0.9, class_id=0)
    assert det.foot_point == (20.0, 100.0)
    assert det.width == 20 and det.height == 80


def test_filters_by_class_and_confidence():
    boxes = [(0, 0, 10, 10), (5, 5, 15, 15), (1, 1, 2, 2), (0, 0, 50, 50)]
    confs = [0.9, 0.2, 0.6, 0.95]
    classes = [0, 0, 7, 0]

    dets = detections_from_arrays(
        boxes, confs, classes, NAMES, confidence_threshold=0.35, keep_class_ids={PERSON_CLASS_ID}
    )

    assert [d.confidence for d in dets] == [0.9, 0.95]
    assert all(d.label == "person" for d in dets)


def test_threshold_is_inclusive():
    dets = detections_from_arrays([(0, 0, 1, 1)], [0.35], [0], NAMES, confidence_threshold=0.35)
    assert len(dets) == 1


def test_keeps_all_classes_when_unfiltered_and_labels_unknown_ids():
    dets = detections_from_arrays(
        [(0, 0, 1, 1), (0, 0, 2, 2)], [0.8, 0.8], [7, 99], NAMES, confidence_threshold=0.1
    )
    assert [d.label for d in dets] == ["truck", "99"]


def test_empty_input_gives_no_detections():
    assert detections_from_arrays([], [], [], NAMES, confidence_threshold=0.5) == []


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        detections_from_arrays([(0, 0, 1, 1)], [0.9, 0.8], [0], NAMES, confidence_threshold=0.1)


def test_draw_detections_does_not_modify_input():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    det = Detection(10, 10, 60, 90, label="person", confidence=0.88, class_id=0)

    out = draw_detections(image, [det])

    assert image.sum() == 0
    assert out.sum() > 0
    assert out.shape == image.shape
