"""Phase 1 / PRD §14: can pretrained YOLO see the target equipment?

Runs the model with *all* COCO classes on sampled frames and reports which
classes it finds. COCO has no excavator, crane or forklift class, so heavy
equipment usually shows up as "truck" or "car" at best, or not at all. That is
why the MVP uses a manually configured danger zone.

Usage:
    uv run python scripts/check_equipment.py data/videos/site.mp4 --samples 20
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2

from constructsafe.annotate import draw_detections
from constructsafe.config import load_config
from constructsafe.detection import create_detector
from constructsafe.sources import VideoFileSource, VideoValidationError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
VEHICLE_LIKE = {"car", "truck", "bus", "train", "boat", "motorcycle"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="video or image file")
    parser.add_argument("--samples", type=int, default=20, help="frames to sample evenly from a video")
    parser.add_argument("--conf", type=float, default=0.25, help="confidence threshold for this check")
    args = parser.parse_args()

    config = load_config()
    config.outputs_dir.mkdir(parents=True, exist_ok=True)
    detector = create_detector(config)

    if args.input.suffix.lower() in IMAGE_EXTENSIONS:
        image = cv2.imread(str(args.input))
        if image is None:
            print(f"error: could not read image {args.input}", file=sys.stderr)
            return 1
        frames = [(0.0, image)]
    else:
        try:
            info = VideoFileSource(args.input, allowed_extensions=config.allowed_video_extensions).info
        except VideoValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        stride = max(info.frame_count // max(args.samples, 1), 1)
        source = VideoFileSource(
            args.input, frame_stride=stride, max_width=config.max_frame_width,
            allowed_extensions=config.allowed_video_extensions,
        )
        frames = [(f.timestamp_seconds, f.image) for f in source][: args.samples]

    seen: dict[str, list[float]] = defaultdict(list)
    for i, (t, image) in enumerate(frames):
        detections = detector.detect(image, confidence_threshold=args.conf)
        for det in detections:
            seen[det.label].append(det.confidence)
        if i == len(frames) // 2:
            out = config.outputs_dir / f"{args.input.stem}_all_classes.jpg"
            cv2.imwrite(str(out), draw_detections(image, detections))
            print(f"sample annotated frame (t={t:.1f}s): {out}")

    print(f"\nclasses found in {len(frames)} frame(s) at conf >= {args.conf}:")
    if not seen:
        print("  (none)")
    for label, confs in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        marker = "  <- vehicle-like" if label in VEHICLE_LIKE else ""
        print(f"  {label:<14} {len(confs):>4} detections, mean conf {sum(confs) / len(confs):.2f}{marker}")
    print(
        "\nCOCO has no excavator/crane/forklift class. If the equipment isn't listed above, "
        "use a manually drawn danger zone (the MVP default). Record the result in docs/ROADMAP.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
