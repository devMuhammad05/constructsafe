"""Glue: frames -> person detection -> zone evaluation -> events -> annotated frames.

No Streamlit here. The UI (Phase 4) and the CLI scripts both drive
:func:`monitor_frames` and decide what to do with each :class:`FrameResult`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from constructsafe.annotate import draw_detections, draw_hazard_banner, draw_status_text, draw_zones
from constructsafe.config import ALERT_LABEL, Config
from constructsafe.detection import Detection, create_detector
from constructsafe.events import EVENT_ADDITIONAL_ENTRY, FrameZoneResult, HazardEvent, ZoneEventEngine
from constructsafe.evidence import safe_name, save_evidence
from constructsafe.sources import Frame, VideoFileSource, VideoValidationError
from constructsafe.storage import STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING, Storage
from constructsafe.video_out import open_video_writer
from constructsafe.zones import DangerZone

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class ProcessingSummary:
    run_id: int
    status: str  # completed or failed
    frames_processed: int
    event_ids: list[int]
    output_path: Path | None
    error_message: str | None = None
    processing_fps: float = 0.0


ProgressCallback = Callable[[int, int], None]  # (frames_processed, expected_frames)


def process_video(
    path: str | Path,
    config: Config,
    storage: Storage,
    *,
    zones: Sequence[DangerZone] | None = None,
    detector: PersonDetector | None = None,
    on_progress: ProgressCallback | None = None,
    on_frame: Callable[[FrameResult], None] | None = None,
    max_frames: int = 0,
    run_id: int | None = None,
) -> ProcessingSummary:
    """Process one video end to end: detect, evaluate zones, save evidence and events.

    Creates a processing run (or takes an existing pending ``run_id``) that
    moves pending -> processing -> completed or failed. Errors are recorded on the run with a readable message rather than
    raised, so callers can show them and offer a retry (a retry is a new run).
    ``zones`` defaults to the zones stored for this video. ``detector`` defaults
    to the configured YOLO model. ``on_frame`` receives every processed
    :class:`FrameResult`, for example to show a live preview.
    """
    path = Path(path)
    if run_id is None:
        run_id = storage.create_run(path.name, str(path))
    frames_processed = 0
    event_ids: list[int] = []
    output_path: Path | None = None
    writer = None
    start = time.perf_counter()

    def fail(message: str) -> ProcessingSummary:
        storage.update_run(
            run_id, status=STATUS_FAILED, error_message=message, frames_processed=frames_processed
        )
        return ProcessingSummary(run_id, STATUS_FAILED, frames_processed, event_ids, output_path, message)

    try:
        source = VideoFileSource(
            path,
            frame_stride=config.frame_stride,
            max_width=config.max_frame_width,
            allowed_extensions=config.allowed_video_extensions,
        )
        if zones is None:
            zones = storage.list_zones(source.name)
        zones = list(zones)
        if not zones:
            return fail(f"No danger zone is configured for {source.name}. Add a zone, then retry.")

        storage.update_run(run_id, status=STATUS_PROCESSING)
        if detector is None:
            detector = create_detector(config)
            detector.warmup()

        info = source.info
        expected = -(-info.frame_count // config.frame_stride) if info.frame_count else 0
        if max_frames:
            expected = min(expected, max_frames) if expected else max_frames
        out_fps = max(info.fps / config.frame_stride, 1.0) if info.fps > 0 else 10.0
        output_stem = config.outputs_dir / f"run{run_id:05d}_{safe_name(path.stem)}_annotated"

        start = time.perf_counter()  # measure processing only, not model loading
        for result in monitor_frames(source, detector, zones, config):
            if writer is None:
                h, w = result.annotated.shape[:2]
                writer, output_path = open_video_writer(output_stem, out_fps, (w, h))
            writer.write(result.annotated)

            for event in result.events:
                try:
                    evidence = save_evidence(
                        config.evidence_dir, result.annotated, run_id=run_id, source_name=source.name, event=event
                    )
                except OSError:
                    # never drop the event because the screenshot failed
                    logger.exception("Evidence capture failed for %s at %.2fs", source.name, event.timestamp_seconds)
                    evidence = None
                event_ids.append(
                    storage.add_event(event, source_name=source.name, run_id=run_id, evidence_path=evidence)
                )

            frames_processed += 1
            if on_progress is not None:
                on_progress(frames_processed, expected)
            if on_frame is not None:
                on_frame(result)
            if frames_processed % 50 == 0:
                storage.update_run(run_id, frames_processed=frames_processed)
            if max_frames and frames_processed >= max_frames:
                break
    except VideoValidationError as exc:
        return fail(str(exc))
    except Exception as exc:  # report any processing failure on the run instead of crashing the app
        logger.exception("Processing failed for %s", path.name)
        return fail(f"Processing failed after {frames_processed} frames: {type(exc).__name__}: {exc}")
    finally:
        if writer is not None:
            writer.release()

    if frames_processed == 0:
        return fail(f"No frames could be read from {path.name}.")

    elapsed = time.perf_counter() - start
    storage.update_run(
        run_id,
        status=STATUS_COMPLETED,
        frames_processed=frames_processed,
        output_path=str(output_path) if output_path else None,
    )
    return ProcessingSummary(
        run_id,
        STATUS_COMPLETED,
        frames_processed,
        event_ids,
        output_path,
        processing_fps=frames_processed / elapsed if elapsed > 0 else 0.0,
    )
