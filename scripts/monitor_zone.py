"""Phase 2: detect workers entering a danger zone in a video.

Zones are polygons in normalised 0-1 image coordinates (0,0 = top-left,
1,1 = bottom-right), so they stay valid if frames are resized.

Usage:
    # preview a zone on the first frame before processing
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zone "0.4,0.5;0.9,0.5;0.9,1;0.4,1" --preview

    # process the video with that zone
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zone "0.4,0.5;0.9,0.5;0.9,1;0.4,1"

    # or load zones from a JSON file: {"zones": [{"zone_id": "excavator", "polygon": [[x, y], ...]}]}
    uv run python scripts/monitor_zone.py data/videos/site.mp4 --zones data/zones/site.json

Writes the annotated video and an events JSON to data/outputs/. Every event is a
potential hazard requiring human review.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from constructsafe.annotate import draw_zones
from constructsafe.config import load_config
from constructsafe.detection import create_detector
from constructsafe.pipeline import monitor_frames
from constructsafe.sources import VideoFileSource, VideoValidationError
from constructsafe.zones import ZoneConfigError, load_zones, parse_zone_arg, zones_for_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="video file")
    group = parser.add_mutually_exclusive_group(required=True)
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
    config.outputs_dir.mkdir(parents=True, exist_ok=True)

    try:
        source = VideoFileSource(
            args.input,
            frame_stride=config.frame_stride,
            max_width=config.max_frame_width,
            allowed_extensions=config.allowed_video_extensions,
        )
        if args.zones:
            zones = zones_for_source(load_zones(args.zones), source.name)
        else:
            zones = [parse_zone_arg(z, zone_id=f"zone-{i + 1}") for i, z in enumerate(args.zone)]
        if not zones:
            raise ZoneConfigError(f"No zones apply to {source.name}")
    except (VideoValidationError, ZoneConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stem = args.input.stem
    if args.preview:
        first = next(iter(source))
        out = config.outputs_dir / f"{stem}_zone_preview.jpg"
        cv2.imwrite(str(out), draw_zones(first.image, zones))
        print(f"saved zone preview: {out}")
        return 0

    detector = create_detector(config)
    detector.warmup()
    info = source.info
    print(f"{source.name}: {info.width}x{info.height}, {info.fps:.1f} fps, {info.frame_count} frames, {len(zones)} zone(s)")

    video_out = config.outputs_dir / f"{stem}_zones.mp4"
    out_fps = max(info.fps / config.frame_stride, 1.0) if info.fps > 0 else 10.0
    writer = None
    events = []
    processed = 0
    start = time.perf_counter()
    try:
        for result in monitor_frames(source, detector, zones, config):
            if writer is None:
                h, w = result.annotated.shape[:2]
                writer = cv2.VideoWriter(str(video_out), cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (w, h))
            writer.write(result.annotated)
            for event in result.events:
                events.append(event)
                print(
                    f"  [{event.timestamp_seconds:7.2f}s] {event.event_type} zone={event.zone_id} "
                    f"workers_in_zone={event.workers_in_zone} latency={event.timestamp_seconds - event.first_seen_seconds:.2f}s"
                    f" - {event.description}"
                )
            for update in result.zones.updates.values():
                if update.cleared:
                    print(f"  [{result.frame.timestamp_seconds:7.2f}s] warning cleared zone={update.zone_id}")
            processed += 1
            if args.max_frames and processed >= args.max_frames:
                break
    finally:
        if writer is not None:
            writer.release()

    elapsed = time.perf_counter() - start
    events_out = config.outputs_dir / f"{stem}_events.json"
    events_out.write_text(
        json.dumps({"source_name": source.name, "events": [asdict(e) for e in events]}, indent=2),
        encoding="utf-8",
    )
    print(
        f"processed {processed} frames in {elapsed:.1f}s ({processed / max(elapsed, 1e-9):.2f} fps); "
        f"{len(events)} potential-hazard event(s)\n  video:  {video_out}\n  events: {events_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
