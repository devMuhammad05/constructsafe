"""Person detection with pretrained Ultralytics YOLO (FR-02).

Only the COCO ``person`` class is kept for workers. No identity, face or other
personal attributes are extracted (PRD §8 Privacy).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from constructsafe.config import Config

PERSON_CLASS_ID = 0  # COCO
PERSON_LABEL = "person"


@dataclass(frozen=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: float
    class_id: int

    @property
    def foot_point(self) -> tuple[float, float]:
        """Bottom-centre of the box: the default point tested against danger zones."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


def detections_from_arrays(
    boxes_xyxy: Iterable[Sequence[float]],
    confidences: Iterable[float],
    class_ids: Iterable[int],
    names: dict[int, str],
    *,
    confidence_threshold: float,
    keep_class_ids: set[int] | None = None,
) -> list[Detection]:
    """Turn raw model outputs into Detections, filtering by class and confidence.

    Kept free of any model dependency so it can be unit-tested with synthetic data.
    """
    detections = []
    for box, conf, cls in zip(boxes_xyxy, confidences, class_ids, strict=True):
        cls = int(cls)
        conf = float(conf)
        if keep_class_ids is not None and cls not in keep_class_ids:
            continue
        if conf < confidence_threshold:
            continue
        x1, y1, x2, y2 = (float(v) for v in box)
        detections.append(
            Detection(x1, y1, x2, y2, label=names.get(cls, str(cls)), confidence=conf, class_id=cls)
        )
    return detections


def _overlap(a: Detection, b: Detection) -> tuple[float, float]:
    """(IoU, intersection / area of the smaller box) for two detections."""
    iw = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    ih = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = iw * ih
    area_a, area_b = a.width * a.height, b.width * b.height
    union = area_a + area_b - inter
    smaller = min(area_a, area_b)
    return (inter / union if union > 0 else 0.0, inter / smaller if smaller > 0 else 0.0)


def suppress_duplicates(
    detections: Iterable[Detection], *, iou_threshold: float, containment_threshold: float
) -> list[Detection]:
    """Drop boxes that are near-copies of a higher-confidence box of the same class.

    YOLO's own NMS sometimes keeps two boxes on one person (one slightly narrower,
    sitting inside the other), which would make a zone count two workers. A box is
    dropped only when it overlaps a kept box with IoU >= ``iou_threshold`` AND at
    least ``containment_threshold`` of the smaller box lies inside the other.
    Requiring both keeps two real, partly overlapping workers apart. A threshold
    of 0 or less disables suppression.
    """
    detections = sorted(detections, key=lambda d: -d.confidence)
    if iou_threshold <= 0 or containment_threshold <= 0:
        return detections
    kept: list[Detection] = []
    for det in detections:
        duplicate = any(
            k.class_id == det.class_id
            and (overlap := _overlap(k, det))[0] >= iou_threshold
            and overlap[1] >= containment_threshold
            for k in kept
        )
        if not duplicate:
            kept.append(det)
    return kept


class YoloDetector:
    """Thin wrapper around an Ultralytics YOLO model."""

    def __init__(
        self,
        weights: str | Path,
        *,
        confidence_threshold: float,
        image_size: int = 640,
        device: str = "cpu",
        duplicate_iou_threshold: float = 0.0,
        duplicate_containment_threshold: float = 0.0,
    ) -> None:
        from ultralytics import YOLO  # imported lazily so pure logic stays light to test

        weights = Path(weights)
        weights.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(weights))
        self.names: dict[int, str] = dict(self.model.names)
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.device = device
        self.duplicate_iou_threshold = duplicate_iou_threshold
        self.duplicate_containment_threshold = duplicate_containment_threshold

    def warmup(self) -> None:
        """Run one blank inference so model start-up cost doesn't skew FPS measurements."""
        self.model.predict(
            np.zeros((self.image_size, self.image_size, 3), dtype=np.uint8),
            imgsz=self.image_size,
            device=self.device,
            verbose=False,
        )

    def detect(
        self,
        image: np.ndarray,
        *,
        keep_class_ids: set[int] | None = None,
        confidence_threshold: float | None = None,
    ) -> list[Detection]:
        threshold = self.confidence_threshold if confidence_threshold is None else confidence_threshold
        result = self.model.predict(
            image,
            conf=threshold,
            imgsz=self.image_size,
            device=self.device,
            classes=sorted(keep_class_ids) if keep_class_ids is not None else None,
            verbose=False,
        )[0]
        boxes = result.boxes
        detections = detections_from_arrays(
            boxes.xyxy.cpu().numpy(),
            boxes.conf.cpu().numpy(),
            boxes.cls.cpu().numpy().astype(int),
            self.names,
            confidence_threshold=threshold,
            keep_class_ids=keep_class_ids,
        )
        return suppress_duplicates(
            detections,
            iou_threshold=self.duplicate_iou_threshold,
            containment_threshold=self.duplicate_containment_threshold,
        )

    def detect_people(self, image: np.ndarray) -> list[Detection]:
        return self.detect(image, keep_class_ids={PERSON_CLASS_ID})


def create_detector(config: Config) -> YoloDetector:
    """Build the detector from a :class:`constructsafe.config.Config`."""
    return YoloDetector(
        config.model_path,
        confidence_threshold=config.confidence_threshold,
        image_size=config.inference_image_size,
        device=config.device,
        duplicate_iou_threshold=config.duplicate_iou_threshold,
        duplicate_containment_threshold=config.duplicate_containment_threshold,
    )
