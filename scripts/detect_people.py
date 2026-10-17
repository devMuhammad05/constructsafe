"""Phase 1: detect and annotate people in a video or image.

Usage:
    uv run python scripts/detect_people.py data/videos/site.mp4
    uv run python scripts/detect_people.py frame.jpg --conf 0.5

Writes the annotated result to data/outputs/ and prints processing speed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from constructsafe.annotate import draw_detections, draw_status_text
from constructsafe.config import load_config
from constructsafe.detection import create_detector
from constructsafe.sources import VideoFileSource, VideoValidationError
from constructsafe.video_out import open_video_writer

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="video or image file")
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
    detector = create_detector(config)

    if args.input.suffix.lower() in IMAGE_EXTENSIONS:
        image = cv2.imread(str(args.input))
        if image is None:
            print(f"error: could not read image {args.input}", file=sys.stderr)
            return 1
        people = detector.detect_people(image)
        out_path = config.outputs_dir / f"{args.input.stem}_people.jpg"
        cv2.imwrite(str(out_path), draw_detections(image, people))
        print(f"{len(people)} person detection(s); saved {out_path}")
        for det in people:
            print(f"  person {det.confidence:.2f} box=({det.x1:.0f},{det.y1:.0f},{det.x2:.0f},{det.y2:.0f})")
        return 0

    try:
        source = VideoFileSource(
            args.input,
            frame_stride=config.frame_stride,
            max_width=config.max_frame_width,
            allowed_extensions=config.allowed_video_extensions,
        )
    except VideoValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    info = source.info
    print(f"{source.name}: {info.width}x{info.height}, {info.fps:.1f} fps, {info.frame_count} frames")
    out_stem = config.outputs_dir / f"{args.input.stem}_people"
    out_path = None
    out_fps = max(info.fps / config.frame_stride, 1.0) if info.fps > 0 else 10.0
    detector.warmup()
    writer = None
    processed = 0
    total_people = 0
    start = time.perf_counter()
    try:
        for frame in source:
            people = detector.detect_people(frame.image)
            total_people += len(people)
            annotated = draw_detections(frame.image, people)
            annotated = draw_status_text(annotated, f"t={frame.timestamp_seconds:6.2f}s  people={len(people)}")
            if writer is None:
                h, w = annotated.shape[:2]
                writer, out_path = open_video_writer(out_stem, out_fps, (w, h))
            writer.write(annotated)
            processed += 1
            if processed % 25 == 0:
                print(f"  {processed} frames, {processed / (time.perf_counter() - start):.1f} fps")
            if args.max_frames and processed >= args.max_frames:
                break
    finally:
        if writer is not None:
            writer.release()

    elapsed = time.perf_counter() - start
    print(
        f"processed {processed} frames in {elapsed:.1f}s ({processed / elapsed:.2f} fps), "
        f"{total_people} person detections; saved {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
