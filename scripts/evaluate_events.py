"""Measure event precision/recall, alert latency and processing FPS on a labelled video.

Write a label file for the video first (see constructsafe/evaluation.py for the format),
then run:

    uv run python scripts/evaluate_events.py data/videos/clip.mp4 --labels data/eval/labels/clip.events.json

The video is processed with the zones from the label file, into a separate evaluation
database under data/eval/ so the dashboard's event history stays clean. The report is
printed and saved to data/eval/reports/. Use --stride / --conf to measure other settings.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from constructsafe.config import load_config
from constructsafe.evaluation import LabelError, PredictedEvent, evaluate_events, load_event_labels
from constructsafe.evidence import safe_name
from constructsafe.pipeline import process_video
from constructsafe.storage import STATUS_COMPLETED, Storage


def fmt(value: float | None, pct: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}" if pct else f"{value:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--labels", type=Path, required=True, help="event label JSON")
    parser.add_argument("--conf", type=float, help="confidence threshold (overrides config)")
    parser.add_argument("--stride", type=int, help="process every Nth frame (overrides config)")
    parser.add_argument("--max-width", type=int, help="downscale frames to this width (overrides config)")
    parser.add_argument("--early-tolerance", type=float, default=0.5, help="seconds an event may fire before the labelled entry")
    parser.add_argument("--max-latency", type=float, default=2.0, help="seconds after the labelled entry an event still counts")
    args = parser.parse_args()

    try:
        labels = load_event_labels(args.labels)
    except LabelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not labels.zones:
        print("error: the label file must define the zones the entries refer to", file=sys.stderr)
        return 1
    if labels.source_name != args.video.name:
        print(f"warning: labels are for {labels.source_name!r} but the video is {args.video.name!r}", file=sys.stderr)

    overrides = {}
    if args.conf is not None:
        overrides["confidence_threshold"] = args.conf
    if args.stride is not None:
        overrides["frame_stride"] = args.stride
    if args.max_width is not None:
        overrides["max_frame_width"] = args.max_width
    base = load_config(**overrides)
    config = replace(base, data_dir=base.data_dir / "eval")  # keep evaluation runs out of the main history
    storage = Storage(config.database_path)

    print(f"processing {args.video.name} with {len(labels.zones)} zone(s), {len(labels.entries)} labelled entr(ies)...")
    summary = process_video(args.video, config, storage, zones=[replace(z, source_name=args.video.name) for z in labels.zones])
    if summary.status != STATUS_COMPLETED:
        print(f"error: processing failed: {summary.error_message}", file=sys.stderr)
        return 1

    events = [
        PredictedEvent(e.zone_id or "", e.timestamp_seconds, e.event_type)
        for e in storage.list_events(run_id=summary.run_id)
    ]
    result = evaluate_events(
        labels.entries, events, early_tolerance=args.early_tolerance, max_latency=args.max_latency
    )
    c = result.counts
    lat = result.latency_summary()

    print(f"\nEvent evaluation: {args.video.name} (run {summary.run_id} in {config.database_path})")
    print(f"  labelled entries: {len(labels.entries)}   predicted events: {len(events)}")
    print(f"  true positives {c.true_positives}, false alarms {c.false_positives}, missed {c.false_negatives}")
    print(f"  precision {fmt(c.precision)}   recall {fmt(c.recall)}   F1 {fmt(c.f1)}")
    print(f"  alert latency (s): mean {fmt(lat['mean'], False)}, median {fmt(lat['median'], False)}, max {fmt(lat['max'], False)}")
    print(f"  processing speed: {summary.processing_fps:.2f} processed frames/s (stride {config.frame_stride})")
    for m in result.missed:
        print(f"  MISSED   zone={m.zone_id} at {m.enter_seconds:.2f}s {m.note}")
    for f in result.false_alarms:
        print(f"  FALSE ALARM zone={f.zone_id} at {f.timestamp_seconds:.2f}s ({f.event_type})")

    report = {
        "video": args.video.name,
        "labels": str(args.labels),
        "labelled_by": labels.labelled_by,
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": summary.run_id,
        "frames_processed": summary.frames_processed,
        "processing_fps": summary.processing_fps,
        "settings": {
            k: v for k, v in asdict(config).items()
            if k in {"model_weights", "confidence_threshold", "inference_image_size", "device", "frame_stride",
                     "max_frame_width", "enter_persistence_frames", "exit_persistence_frames"}
        },
        "events": result.as_dict(),
    }
    reports = config.data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = reports / f"{safe_name(args.video.stem)}_events_{stamp}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
