"""Zone-entry state machine and duplicate suppression (FR-04, FR-06).

Each zone tracks a *confirmed* number of workers inside it. The raw per-frame
count only changes the confirmed count after it has held for several
consecutive processed frames:

* count rises and holds for ``enter_frames`` -> confirmed count goes up and a
  potential-hazard event is emitted (``danger_zone_entry`` when the zone was
  empty, ``additional_worker_entry`` when it already had workers in it);
* count falls and holds for ``exit_frames`` -> confirmed count goes down; when
  it reaches 0 the warning clears.

This means one event per interaction rather than one per frame. A worker
missing for a few frames (occlusion, a dropped detection) doesn't end the
interaction, and a one-frame false detection doesn't start one. It works
without person tracking, so tracker ID switches can't cause duplicate alerts.
The cost is that it relies on counts: if one worker leaves just as another
enters within the persistence window, it may not register a new entry.

Persistence is counted in *processed* frames, so with ``frame_stride`` > 1 the
same setting covers more video time. Alert latency is about ``enter_frames``
processed frames after the first visible entry.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from constructsafe.detection import Detection
from constructsafe.zones import DangerZone

HAZARD_DESCRIPTION = "Potential hazard requiring human review"

EVENT_ZONE_ENTRY = "danger_zone_entry"
EVENT_ADDITIONAL_ENTRY = "additional_worker_entry"


@dataclass(frozen=True)
class HazardEvent:
    zone_id: str
    event_type: str
    frame_index: int  # frame at which the entry was confirmed (the evidence frame)
    timestamp_seconds: float  # video position of that frame
    first_seen_seconds: float  # when the raw count first rose; latency = timestamp - this
    workers_in_zone: int
    workers_entered: int
    description: str = HAZARD_DESCRIPTION


@dataclass(frozen=True)
class ZoneUpdate:
    zone_id: str
    raw_count: int  # workers inside on this frame, before smoothing
    confirmed_count: int  # smoothed count driving the warning
    events: tuple[HazardEvent, ...] = ()
    cleared: bool = False  # warning ended on this frame

    @property
    def active(self) -> bool:
        return self.confirmed_count > 0


@dataclass
class ZoneOccupancyMonitor:
    """Hysteresis over the number of workers inside one zone."""

    zone_id: str
    enter_frames: int = 3
    exit_frames: int = 5
    confirmed_count: int = 0
    _direction: int = 0  # +1 rising, -1 falling, 0 stable
    _window: list[int] = field(default_factory=list)
    _window_start_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.enter_frames < 1 or self.exit_frames < 1:
            raise ValueError("enter_frames and exit_frames must be at least 1")

    @property
    def active(self) -> bool:
        return self.confirmed_count > 0

    def _reset_pending(self) -> None:
        self._direction = 0
        self._window = []

    def update(self, frame_index: int, timestamp_seconds: float, raw_count: int) -> ZoneUpdate:
        if raw_count < 0:
            raise ValueError("raw_count cannot be negative")

        direction = (raw_count > self.confirmed_count) - (raw_count < self.confirmed_count)
        if direction == 0:
            self._reset_pending()
            return ZoneUpdate(self.zone_id, raw_count, self.confirmed_count)

        if direction != self._direction:
            self._direction = direction
            self._window = []
            self._window_start_seconds = timestamp_seconds
        self._window.append(raw_count)

        events: tuple[HazardEvent, ...] = ()
        cleared = False
        if direction > 0 and len(self._window) >= self.enter_frames:
            # the smallest count seen throughout the window is the one that actually held
            new_count = min(self._window)
            events = (
                HazardEvent(
                    zone_id=self.zone_id,
                    event_type=EVENT_ZONE_ENTRY if self.confirmed_count == 0 else EVENT_ADDITIONAL_ENTRY,
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                    first_seen_seconds=self._window_start_seconds,
                    workers_in_zone=new_count,
                    workers_entered=new_count - self.confirmed_count,
                ),
            )
            self.confirmed_count = new_count
            self._reset_pending()
        elif direction < 0 and len(self._window) >= self.exit_frames:
            # the largest count seen throughout the window: be slow to declare people gone
            self.confirmed_count = max(self._window)
            cleared = self.confirmed_count == 0
            self._reset_pending()

        return ZoneUpdate(self.zone_id, raw_count, self.confirmed_count, events, cleared)


@dataclass(frozen=True)
class FrameZoneResult:
    updates: dict[str, ZoneUpdate]
    workers_in_zones: dict[str, tuple[Detection, ...]]  # zone_id -> detections whose feet are inside

    @property
    def events(self) -> list[HazardEvent]:
        return [e for u in self.updates.values() for e in u.events]

    @property
    def active_zone_ids(self) -> list[str]:
        return [zid for zid, u in self.updates.items() if u.active]

    def is_in_any_zone(self, detection: Detection) -> bool:
        return any(detection in dets for dets in self.workers_in_zones.values())


class ZoneEventEngine:
    """Runs one :class:`ZoneOccupancyMonitor` per configured zone."""

    def __init__(self, zones: Sequence[DangerZone], *, enter_frames: int, exit_frames: int) -> None:
        ids = [z.zone_id for z in zones]
        if len(ids) != len(set(ids)):
            raise ValueError("zone_id values must be unique")
        self.zones = list(zones)
        self.monitors = {
            z.zone_id: ZoneOccupancyMonitor(z.zone_id, enter_frames=enter_frames, exit_frames=exit_frames)
            for z in self.zones
        }

    def update(
        self,
        frame_index: int,
        timestamp_seconds: float,
        people: Iterable[Detection],
        frame_width: int,
        frame_height: int,
    ) -> FrameZoneResult:
        people = list(people)
        updates: dict[str, ZoneUpdate] = {}
        inside: dict[str, tuple[Detection, ...]] = {}
        for zone in self.zones:
            in_zone = tuple(
                p for p in people if zone.contains_pixel(p.foot_point, frame_width, frame_height)
            )
            inside[zone.zone_id] = in_zone
            updates[zone.zone_id] = self.monitors[zone.zone_id].update(
                frame_index, timestamp_seconds, len(in_zone)
            )
        return FrameZoneResult(updates=updates, workers_in_zones=inside)
