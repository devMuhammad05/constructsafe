"""Glue: frames -> person detection -> zone evaluation -> events -> annotated frames.

No Streamlit here. The UI (Phase 4) and the CLI scripts both drive
:func:`monitor_frames` and decide what to do with each :class:`FrameResult`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from constructsafe.annotate import draw_detections, draw_hazard_banner, draw_status_text, draw_zones
from constructsafe.config import ALERT_LABEL, Config
from constructsafe.detection import Detection
from constructsafe.events import EVENT_ADDITIONAL_ENTRY, FrameZoneResult, HazardEvent, ZoneEventEngine
from constructsafe.sources import Frame
from constructsafe.zones import DangerZone

EVENT_TYPE_LABELS = {
    "danger_zone_entry": "Worker entered danger zone",
    EVENT_ADDITIONAL_ENTRY: "Additional worker entered danger zone",
}


class PersonDetector(Protocol):
    def detect_people(self, image: np.ndarray) -> list[Detection]: ...


@dataclass(frozen=True)
class FrameResult:
    frame: Frame
    people: list[Detection]
    zones: FrameZoneResult
    annotated: np.ndarray

    @property
    def events(self) -> list[HazardEvent]:
        return self.zones.events


def banner_lines(
    zones: Sequence[DangerZone], zone_result: FrameZoneResult, last_events: dict[str, HazardEvent]
) -> list[str]:
    active = zone_result.active_zone_ids
    if not active:
        return []
    lines = [ALERT_LABEL.upper()]
    names = {z.zone_id: z.name for z in zones}
    for zone_id in active:
        event = last_events.get(zone_id)
        count = zone_result.updates[zone_id].confirmed_count
        what = EVENT_TYPE_LABELS.get(event.event_type, event.event_type) if event else "Worker in danger zone"
        when = f" at {event.timestamp_seconds:.1f}s" if event else ""
        lines.append(f"{what}: {names.get(zone_id, zone_id)}{when} ({count} inside)")
    return lines


def annotate_frame(
    frame: Frame,
    people: Sequence[Detection],
    zones: Sequence[DangerZone],
    zone_result: FrameZoneResult,
    last_events: dict[str, HazardEvent],
) -> np.ndarray:
    active = set(zone_result.active_zone_ids)
    hazard_people = {p for zid in active for p in zone_result.workers_in_zones[zid]}
    image = draw_zones(frame.image, zones, active_zone_ids=active)
    image = draw_detections(image, people, hazard_detections=hazard_people)
    image = draw_hazard_banner(image, banner_lines(zones, zone_result, last_events))
    return draw_status_text(image, f"t={frame.timestamp_seconds:6.2f}s  people={len(people)}")


def monitor_frames(
    frames: Iterable[Frame],
    detector: PersonDetector,
    zones: Sequence[DangerZone],
    config: Config,
) -> Iterator[FrameResult]:
    """Process frames one at a time. Works with any frame source, live or recorded."""
    engine = ZoneEventEngine(
        zones,
        enter_frames=config.enter_persistence_frames,
        exit_frames=config.exit_persistence_frames,
    )
    last_events: dict[str, HazardEvent] = {}
    for frame in frames:
        height, width = frame.image.shape[:2]
        people = detector.detect_people(frame.image)
        zone_result = engine.update(frame.index, frame.timestamp_seconds, people, width, height)
        for event in zone_result.events:
            last_events[event.zone_id] = event
        for zone_id, update in zone_result.updates.items():
            if update.cleared:
                last_events.pop(zone_id, None)
        annotated = annotate_frame(frame, people, zones, zone_result, last_events)
        yield FrameResult(frame=frame, people=people, zones=zone_result, annotated=annotated)
