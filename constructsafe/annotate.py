"""Drawing helpers for annotated frames.

All functions return a new image and leave the input untouched, so the same raw
frame can be reused for evidence capture.
"""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

from constructsafe.detection import Detection

# BGR colours
PERSON_COLOR = (0, 200, 0)
OTHER_COLOR = (200, 160, 0)
TEXT_COLOR = (255, 255, 255)

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label_box(image: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    scale, thickness = 0.5, 1
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, thickness)
    top = max(y - th - baseline - 4, 0)
    cv2.rectangle(image, (x, top), (x + tw + 6, top + th + baseline + 4), color, cv2.FILLED)
    cv2.putText(image, text, (x + 3, top + th + 2), FONT, scale, TEXT_COLOR, thickness, cv2.LINE_AA)


def draw_detections(
    image: np.ndarray,
    detections: Iterable[Detection],
    *,
    color: tuple[int, int, int] | None = None,
    show_foot_point: bool = True,
) -> np.ndarray:
    """Draw a box, label and confidence for each detection (FR-02)."""
    out = image.copy()
    for det in detections:
        box_color = color or (PERSON_COLOR if det.label == "person" else OTHER_COLOR)
        p1 = (round(det.x1), round(det.y1))
        p2 = (round(det.x2), round(det.y2))
        cv2.rectangle(out, p1, p2, box_color, 2)
        _label_box(out, f"{det.label} {det.confidence:.2f}", p1[0], p1[1], box_color)
        if show_foot_point:
            fx, fy = det.foot_point
            cv2.circle(out, (round(fx), round(fy)), 4, box_color, cv2.FILLED)
    return out


def draw_status_text(image: np.ndarray, text: str) -> np.ndarray:
    """Small status line in the top-left corner (frame time, counts)."""
    out = image.copy()
    _label_box(out, text, 8, 28, (40, 40, 40))
    return out
