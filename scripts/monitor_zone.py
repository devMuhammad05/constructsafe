"""Detect workers entering danger zones in a video and log the events.

Zones are polygons in normalised 0-1 image coordinates (0,0 = top-left,
1,1 = bottom-right), so they stay valid if frames are resized. Zones given on
the command line are saved to the database for that video, so later runs
can omit them.

Usage:
    # preview a zone on the first frame before processing
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zone "0.4,0.5;0.9,0.5;0.9,1;0.4,1" --preview

    # process the video with that zone (and remember it for site.mp4)
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zone "0.4,0.5;0.9,0.5;0.9,1;0.4,1"

    # reuse the stored zones, or load them from a JSON file
    uv run python scripts/monitor_zone.py data/videos/site.mp4
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zones data/zones/site.json

Events go to the SQLite database, evidence screenshots to data/evidence/, and
the annotated video to data/outputs/. Every event is a potential hazard
requiring human review.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import cv2

from constructsafe.annotate import draw_zones
from constructsafe.config import load_config
from constructsafe.pipeline import process_video
from constructsafe.sources import VideoFileSource, VideoValidationError
from constructsafe.storage import STATUS_COMPLETED, Storage
from constructsafe.zones import ZoneConfigError, load_zones, parse_zone_arg, zones_for_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="video file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--zone", action="append", help='normalised polygon "x1,y1;x2,y2;x3,y3" (repeatable)')
    group.add_argument("--zones", type=Path, help="JSON file with zone definitions")
    parser.add_argument("--preview", action="store_true", help="save the first frame with zones drawn, then exit")
    parser.add_argument("--conf", type=float, help="confidence threshold (overrides config)")
    parser.add_argument("--stride", type=int, help="process every Nth frame (overrides config)")
    parser.add_argument("--max-frames", type=int, default=0, help="stop after N processed frames")
    args = parser.parse_args()

    overrides = {}
    if args.conf is not None:
        overrides["confidence_threshold"] = args.conf
    if args.stride is not None:
        overrides["frame_stride"] = args.stride
    config = load_config(**overrides)
    storage = Storage(config.database_path)
    source_name = args.input.name

    try:
        if args.zones:
            zones = zones_for_source(load_zones(args.zones), source_name)
        elif args.zone:
            zones = [
                parse_zone_arg(z, zone_id=f"zone-{i + 1}", source_name=source_name)
                for i, z in enumerate(args.zone)
            ]
        else:
            zones = storage.list_zones(source_name)
        if not zones:
            raise ZoneConfigError(f"No zones for {source_name}: pass --zone or --zones")
    except ZoneConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.preview:
        try:
            source = VideoFileSource(
                args.input, max_width=config.max_frame_width, allowed_extensions=config.allowed_video_extensions
            )
        except VideoValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        config.outputs_dir.mkdir(parents=True, exist_ok=True)
        out = config.outputs_dir / f"{args.input.stem}_zone_preview.jpg"
        cv2.imwrite(str(out), draw_zones(next(iter(source)).image, zones))
        print(f"saved zone preview: {out}")
        return 0

    if args.zone or args.zones:
        for zone in zones:
            storage.save_zone(zone if zone.source_name else replace(zone, source_name=source_name))

    def progress(done: int, expected: int) -> None:
        if done % 25 == 0:
            print(f"  {done}/{expected or '?'} frames")

    print(f"processing {source_name} with {len(zones)} zone(s)...")
    summary = process_video(
        args.input, config, storage, zones=zones, on_progress=progress, max_frames=args.max_frames
    )
    run = storage.get_run(summary.run_id)
    print(f"run {summary.run_id}: {run.status}")
    if summary.status != STATUS_COMPLETED:
        print(f"error: {summary.error_message}", file=sys.stderr)
        return 1

    for event in storage.list_events(run_id=summary.run_id):
        first_seen = event.first_seen_seconds if event.first_seen_seconds is not None else event.timestamp_seconds
        latency = event.timestamp_seconds - first_seen
        print(
            f"  #{event.id} [{event.timestamp_seconds:7.2f}s] {event.event_type} zone={event.zone_id} "
            f"workers_in_zone={event.workers_in_zone} latency={latency:.2f}s evidence={event.evidence_path}"
        )
    print(
        f"processed {summary.frames_processed} frames ({summary.processing_fps:.2f} fps); "
        f"{len(summary.event_ids)} potential-hazard event(s) requiring human review\n"
        f"  video:    {summary.output_path}\n  database: {config.database_path}\n  evidence: {config.evidence_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
