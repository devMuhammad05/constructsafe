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


class YoloDetector:
    """Thin wrapper around an Ultralytics YOLO model."""

    def __init__(
        self,
        weights: str | Path,
        *,
        confidence_threshold: float,
        image_size: int = 640,
        device: str = "cpu",
    ) -> None:
        from ultralytics import YOLO  # imported lazily so pure logic stays light to test

        weights = Path(weights)
        weights.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(weights))
        self.names: dict[int, str] = dict(self.model.names)
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.device = device

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
        return detections_from_arrays(
            boxes.xyxy.cpu().numpy(),
            boxes.conf.cpu().numpy(),
            boxes.cls.cpu().numpy().astype(int),
            self.names,
            confidence_threshold=threshold,
            keep_class_ids=keep_class_ids,
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
    )
