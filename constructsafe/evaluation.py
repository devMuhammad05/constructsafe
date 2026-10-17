"""Evaluation against hand-labelled ground truth (PRD §13). No model or video needed.

Two kinds of labels, both JSON and both in normalised 0-1 coordinates where
positions are involved:

**Event labels**: when a worker visibly enters a danger zone::

    {
      "source_name": "pexels_33769531_vladimir-srajber.mp4",
      "zones": [{"zone_id": "excavator", "name": "Excavator", "polygon": [[x, y], ...]}],
      "entries": [{"zone_id": "excavator", "enter_seconds": 12.4, "note": "worker from left"}],
      "labelled_by": "initials", "notes": "..."
    }

Each entry is one worker entering, whether the zone was empty or not. A predicted event
matches an entry in the same zone if it fires between ``early_tolerance`` seconds before
and ``max_latency`` seconds after the labelled entry. Matching is one-to-one, in time
order.

**Detection labels**: person boxes on selected frames::

    {"source_name": "...", "frames": [{"frame_index": 30, "people": [[x1, y1, x2, y2], ...]}]}

A detection is a true positive when its IoU with an unmatched labelled box is at least
``iou_threshold``. Matching is greedy by confidence, as in standard detection benchmarks.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from constructsafe.detection import Detection
from constructsafe.zones import DangerZone

Box = tuple[float, float, float, float]


class LabelError(ValueError):
    """Raised for malformed label files."""


# --- shared -------------------------------------------------------------------


@dataclass(frozen=True)
class PrecisionRecall:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float | None:
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else None

    @property
    def recall(self) -> float | None:
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    def __add__(self, other: PrecisionRecall) -> PrecisionRecall:
        return PrecisionRecall(
            self.true_positives + other.true_positives,
            self.false_positives + other.false_positives,
            self.false_negatives + other.false_negatives,
        )

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def _load_json(path: str | Path) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelError(f"Could not read label file {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise LabelError(f"Label file {path.name} must contain a JSON object")
    return data


# --- events -------------------------------------------------------------------


@dataclass(frozen=True)
class LabelledEntry:
    zone_id: str
    enter_seconds: float
    note: str = ""


@dataclass(frozen=True)
class PredictedEvent:
    zone_id: str
    timestamp_seconds: float
    event_type: str = ""


@dataclass(frozen=True)
class EventLabels:
    source_name: str
    zones: tuple[DangerZone, ...]
    entries: tuple[LabelledEntry, ...]
    labelled_by: str = ""
    notes: str = ""


def load_event_labels(path: str | Path) -> EventLabels:
    data = _load_json(path)
    try:
        source_name = str(data["source_name"])
        zones = tuple(
            DangerZone.from_dict({**z, "source_name": z.get("source_name", source_name)})
            for z in data.get("zones", [])
        )
        entries = tuple(
            LabelledEntry(str(e["zone_id"]), float(e["enter_seconds"]), str(e.get("note", "")))
            for e in data.get("entries", [])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LabelError(f"Invalid event label file: {exc}") from exc
    zone_ids = {z.zone_id for z in zones}
    unknown = {e.zone_id for e in entries} - zone_ids
    if zones and unknown:
        raise LabelError(f"Entries refer to zones that aren't defined: {sorted(unknown)}")
    return EventLabels(
        source_name, zones, entries, str(data.get("labelled_by", "")), str(data.get("notes", ""))
    )


@dataclass(frozen=True)
class EventMatch:
    entry: LabelledEntry
    event: PredictedEvent

    @property
    def latency_seconds(self) -> float:
        return self.event.timestamp_seconds - self.entry.enter_seconds


@dataclass(frozen=True)
class EventEvaluation:
    counts: PrecisionRecall
    matches: tuple[EventMatch, ...]
    missed: tuple[LabelledEntry, ...]  # false negatives: hazards the system didn't flag
    false_alarms: tuple[PredictedEvent, ...]  # false positives
    early_tolerance: float
    max_latency: float

    @property
    def latencies(self) -> list[float]:
        return [m.latency_seconds for m in self.matches]

    def latency_summary(self) -> dict:
        lat = self.latencies
        if not lat:
            return {"count": 0, "mean": None, "median": None, "max": None}
        return {"count": len(lat), "mean": statistics.fmean(lat), "median": statistics.median(lat), "max": max(lat)}

    def as_dict(self) -> dict:
        return {
            **self.counts.as_dict(),
            "alert_latency_seconds": self.latency_summary(),
            "matching": {"early_tolerance": self.early_tolerance, "max_latency": self.max_latency},
            "missed_entries": [{"zone_id": e.zone_id, "enter_seconds": e.enter_seconds, "note": e.note} for e in self.missed],
            "false_alarms": [
                {"zone_id": e.zone_id, "timestamp_seconds": e.timestamp_seconds, "event_type": e.event_type}
                for e in self.false_alarms
            ],
            "matches": [
                {"zone_id": m.entry.zone_id, "enter_seconds": m.entry.enter_seconds,
                 "event_seconds": m.event.timestamp_seconds, "latency_seconds": m.latency_seconds}
                for m in self.matches
            ],
        }


def evaluate_events(
    entries: Iterable[LabelledEntry],
    events: Iterable[PredictedEvent],
    *,
    early_tolerance: float = 0.5,
    max_latency: float = 2.0,
) -> EventEvaluation:
    """Match predicted events to labelled entries, one-to-one, per zone, in time order.

    For each labelled entry (earliest first), take the earliest unmatched event in the
    same zone inside ``[enter - early_tolerance, enter + max_latency]``.
    """
    if early_tolerance < 0 or max_latency < 0:
        raise ValueError("tolerances must be non-negative")
    entries = sorted(entries, key=lambda e: e.enter_seconds)
    events = sorted(events, key=lambda e: e.timestamp_seconds)
    used: set[int] = set()
    matches: list[EventMatch] = []
    missed: list[LabelledEntry] = []
    for entry in entries:
        lo, hi = entry.enter_seconds - early_tolerance, entry.enter_seconds + max_latency
        chosen = next(
            (i for i, ev in enumerate(events)
             if i not in used and ev.zone_id == entry.zone_id and lo <= ev.timestamp_seconds <= hi),
            None,
        )
        if chosen is None:
            missed.append(entry)
        else:
            used.add(chosen)
            matches.append(EventMatch(entry, events[chosen]))
    false_alarms = [ev for i, ev in enumerate(events) if i not in used]
    counts = PrecisionRecall(len(matches), len(false_alarms), len(missed))
    return EventEvaluation(counts, tuple(matches), tuple(missed), tuple(false_alarms), early_tolerance, max_latency)


# --- detection ----------------------------------------------------------------


@dataclass(frozen=True)
class FrameLabels:
    frame_index: int
    people: tuple[Box, ...]  # normalised xyxy


@dataclass(frozen=True)
class DetectionLabels:
    source_name: str
    frames: tuple[FrameLabels, ...]
    labelled_by: str = ""


def load_detection_labels(path: str | Path) -> DetectionLabels:
    data = _load_json(path)
    try:
        frames = []
        for f in data["frames"]:
            boxes = []
            for b in f.get("people", []):
                x1, y1, x2, y2 = (float(v) for v in b)
                if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                    raise ValueError(f"box {b} on frame {f['frame_index']} isn't a normalised x1<x2, y1<y2 box")
                boxes.append((x1, y1, x2, y2))
            frames.append(FrameLabels(int(f["frame_index"]), tuple(boxes)))
        return DetectionLabels(str(data["source_name"]), tuple(frames), str(data.get("labelled_by", "")))
    except (KeyError, TypeError, ValueError) as exc:
        raise LabelError(f"Invalid detection label file: {exc}") from exc


def iou(a: Box, b: Box) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def normalise_detection(det: Detection, width: int, height: int) -> Box:
    return (det.x1 / width, det.y1 / height, det.x2 / width, det.y2 / height)


@dataclass
class DetectionEvaluation:
    iou_threshold: float
    per_frame: dict[int, PrecisionRecall] = field(default_factory=dict)

    @property
    def counts(self) -> PrecisionRecall:
        total = PrecisionRecall(0, 0, 0)
        for pr in self.per_frame.values():
            total = total + pr
        return total

    def as_dict(self) -> dict:
        return {
            **self.counts.as_dict(),
            "iou_threshold": self.iou_threshold,
            "frames_evaluated": len(self.per_frame),
            "per_frame": {str(k): v.as_dict() for k, v in sorted(self.per_frame.items())},
        }


def match_frame(
    predicted: Sequence[tuple[Box, float]], labelled: Sequence[Box], *, iou_threshold: float = 0.5
) -> PrecisionRecall:
    """Greedy matching by descending confidence. ``predicted`` is ``(box, confidence)``."""
    unmatched = list(range(len(labelled)))
    tp = fp = 0
    for box, _conf in sorted(predicted, key=lambda p: -p[1]):
        best, best_iou = None, iou_threshold
        for j in unmatched:
            overlap = iou(box, labelled[j])
            if overlap >= best_iou:
                best, best_iou = j, overlap
        if best is None:
            fp += 1
        else:
            unmatched.remove(best)
            tp += 1
    return PrecisionRecall(tp, fp, len(unmatched))
