"""Drawing helpers for annotated frames.

All functions return a new image and leave the input untouched, so the same raw
frame can be reused for evidence capture.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

import cv2
import numpy as np

from constructsafe.detection import Detection
from constructsafe.zones import DangerZone

# BGR colours
PERSON_COLOR = (0, 200, 0)
OTHER_COLOR = (200, 160, 0)
HAZARD_COLOR = (0, 0, 230)
ZONE_IDLE_COLOR = (0, 200, 255)
TEXT_COLOR = (255, 255, 255)

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label_box(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    scale: float = 0.5,
    thickness: int = 1,
) -> None:
    (tw, th), baseline = cv2.getTextSize(text, FONT, scale, thickness)
    top = max(y - th - baseline - 4, 0)
    cv2.rectangle(image, (x, top), (x + tw + 6, top + th + baseline + 4), color, cv2.FILLED)
    cv2.putText(image, text, (x + 3, top + th + 2), FONT, scale, TEXT_COLOR, thickness, cv2.LINE_AA)


def draw_detections(
    image: np.ndarray,
    detections: Iterable[Detection],
    *,
    hazard_detections: Collection[Detection] = (),
    show_foot_point: bool = True,
) -> np.ndarray:
    """Draw a box, label and confidence for each detection (FR-02).

    Detections in ``hazard_detections`` (workers inside an active zone) are drawn
    in the hazard colour with a thicker box so they stand out (FR-05).
    """
    out = image.copy()
    for det in detections:
        hazard = det in hazard_detections
        if hazard:
            box_color, thickness = HAZARD_COLOR, 3
        else:
            box_color, thickness = (PERSON_COLOR if det.label == "person" else OTHER_COLOR), 2
        p1 = (round(det.x1), round(det.y1))
        p2 = (round(det.x2), round(det.y2))
        cv2.rectangle(out, p1, p2, box_color, thickness)
        _label_box(out, f"{det.label} {det.confidence:.2f}", p1[0], p1[1], box_color)
        if show_foot_point:
            fx, fy = det.foot_point
            cv2.circle(out, (round(fx), round(fy)), 5 if hazard else 4, box_color, cv2.FILLED)
    return out


def draw_zones(
    image: np.ndarray,
    zones: Iterable[DangerZone],
    *,
    active_zone_ids: Collection[str] = (),
    fill_alpha: float = 0.25,
) -> np.ndarray:
    """Overlay each zone as a translucent polygon: amber when idle, red when occupied."""
    out = image.copy()
    height, width = out.shape[:2]
    overlay = out.copy()
    outlines = []
    for zone in zones:
        pts = np.array(zone.pixel_polygon(width, height), dtype=np.int32)
        color = HAZARD_COLOR if zone.zone_id in active_zone_ids else ZONE_IDLE_COLOR
        cv2.fillPoly(overlay, [pts], color)
        outlines.append((zone, pts, color))
    cv2.addWeighted(overlay, fill_alpha, out, 1 - fill_alpha, 0, dst=out)
    for zone, pts, color in outlines:
        cv2.polylines(out, [pts], isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA)
        x, y = pts.min(axis=0)
        _label_box(out, f"Danger zone: {zone.name}", int(x), int(y), color)
    return out


def draw_hazard_banner(image: np.ndarray, lines: Iterable[str]) -> np.ndarray:
    """Red warning banner across the top of the frame (FR-05)."""
    out = image.copy()
    lines = list(lines)
    if not lines:
        return out
    width = out.shape[1]
    scale = max(0.5, min(1.0, width / 1400))
    line_height = int(34 * scale) + 6
    banner_height = line_height * len(lines) + 10
    cv2.rectangle(out, (0, 0), (width, banner_height), HAZARD_COLOR, cv2.FILLED)
    for i, text in enumerate(lines):
        y = 8 + line_height * (i + 1) - 8
        cv2.putText(out, text, (12, y), FONT, scale, TEXT_COLOR, 2 if i == 0 else 1, cv2.LINE_AA)
    return out


def draw_status_text(image: np.ndarray, text: str) -> np.ndarray:
    """Small status line in the bottom-left corner (frame time, counts)."""
    out = image.copy()
    _label_box(out, text, 8, out.shape[0] - 8, (40, 40, 40))
    return out
