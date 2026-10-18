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


# --- duplicate suppression ------------------------------------------------------

from constructsafe.detection import suppress_duplicates  # noqa: E402


def person(x1, y1, x2, y2, conf, cls=0):
    return Detection(x1, y1, x2, y2, label="person" if cls == 0 else "truck", confidence=conf, class_id=cls)


def dedupe(dets):
    return suppress_duplicates(dets, iou_threshold=0.55, containment_threshold=0.85)


@pytest.mark.parametrize(
    "a, b",
    [
        # real duplicate pairs measured on the Pexels 33769531 clip (frames 1458, 1460, 1618, 1620)
        ((428, 426, 463, 525, 0.48), (428, 425, 486, 526, 0.47)),
        ((430, 423, 488, 527, 0.63), (431, 424, 472, 526, 0.38)),
        ((397, 420, 464, 528, 0.74), (394, 420, 445, 529, 0.50)),
        ((391, 420, 467, 528, 0.60), (385, 422, 447, 528, 0.59)),
    ],
)
def test_measured_duplicates_collapse_to_the_higher_confidence_box(a, b):
    kept = dedupe([person(*a), person(*b)])
    assert len(kept) == 1
    assert kept[0].confidence == max(a[4], b[4])


def test_two_workers_side_by_side_are_kept():
    # shoulders overlap a little (IoU ~0.1)
    assert len(dedupe([person(100, 100, 150, 250, 0.8), person(140, 100, 190, 250, 0.7)])) == 2


def test_worker_partly_behind_another_is_kept():
    # rear worker's box is mostly inside the front one, but much smaller: IoU stays low
    front = person(100, 100, 160, 260, 0.9)
    rear = person(120, 110, 150, 200, 0.6)
    assert len(dedupe([front, rear])) == 2


def test_different_classes_are_never_merged():
    assert len(dedupe([person(0, 0, 10, 10, 0.9), person(0, 0, 10, 10, 0.8, cls=7)])) == 2


def test_suppression_can_be_disabled():
    a, b = person(428, 426, 463, 525, 0.48), person(428, 425, 486, 526, 0.47)
    assert len(suppress_duplicates([a, b], iou_threshold=0, containment_threshold=0)) == 2
