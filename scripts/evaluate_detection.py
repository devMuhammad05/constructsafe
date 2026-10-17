"""Measure person-detection precision/recall against hand-drawn boxes.

Step 1: export evenly spaced frames and an empty label template:

    uv run python scripts/evaluate_detection.py export data/videos/clip.mp4 --count 20

  This writes JPEGs to data/eval/frames/<clip>/ and a template to
  data/eval/labels/<clip>.detection.json. For each frame, fill "people" with one
  [x1, y1, x2, y2] box per visible worker, as fractions of the frame width/height
  (any annotation tool works; convert pixel boxes by dividing by the image size).
  Label every person you can see, including partly hidden ones.

Step 2: compare the model with the labels:

    uv run python scripts/evaluate_detection.py run data/videos/clip.mp4 --labels data/eval/labels/clip.detection.json

  Precision/recall are reported at several confidence thresholds, so the report
  also shows how the threshold trades false alarms against missed workers.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import cv2

from constructsafe.config import load_config
from constructsafe.detection import PERSON_CLASS_ID, create_detector
from constructsafe.evaluation import (
    DetectionEvaluation,
    LabelError,
    load_detection_labels,
    match_frame,
    normalise_detection,
)
from constructsafe.evidence import safe_name
from constructsafe.sources import VideoValidationError, read_frame, validate_video_file

THRESHOLDS = (0.15, 0.25, 0.35, 0.5, 0.65)


def export(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        info = validate_video_file(args.video, config.allowed_video_extensions)
    except VideoValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    count = max(1, min(args.count, info.frame_count))
    step = info.frame_count / count
    indices = sorted({int(step * i + step / 2) for i in range(count)})

    eval_dir = config.data_dir / "eval"
    frames_dir = eval_dir / "frames" / safe_name(args.video.stem)
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i in indices:
        frame = read_frame(args.video, i)
        cv2.imwrite(str(frames_dir / f"frame_{i:06d}.jpg"), frame.image)

    template = eval_dir / "labels" / f"{safe_name(args.video.stem)}.detection.json"
    if template.exists() and not args.force:
        print(f"error: {template} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(
        json.dumps(
            {
                "source_name": args.video.name,
                "labelled_by": "",
                "image_size": [info.width, info.height],
                "frames": [{"frame_index": i, "image": f"frame_{i:06d}.jpg", "people": []} for i in indices],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"exported {len(indices)} frames to {frames_dir}\nlabel template: {template}")
    return 0


def run(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        labels = load_detection_labels(args.labels)
    except LabelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not labels.frames:
        print("error: the label file has no frames", file=sys.stderr)
        return 1

    detector = create_detector(config)
    # detect once at a low threshold, then filter for each threshold being compared
    floor = min(THRESHOLDS)
    predictions: dict[int, list] = {}
    for f in labels.frames:
        frame = read_frame(args.video, f.frame_index)
        h, w = frame.image.shape[:2]
        dets = detector.detect(frame.image, keep_class_ids={PERSON_CLASS_ID}, confidence_threshold=floor)
        predictions[f.frame_index] = [(normalise_detection(d, w, h), d.confidence) for d in dets]

    total_people = sum(len(f.people) for f in labels.frames)
    print(f"{args.video.name}: {len(labels.frames)} labelled frames, {total_people} labelled people, IoU >= {args.iou}\n")
    print(f"  {'conf':>5}  {'TP':>4} {'FP':>4} {'FN':>4}  {'precision':>9} {'recall':>7}")
    report = {"video": args.video.name, "labels": str(args.labels), "labelled_by": labels.labelled_by,
              "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
              "model_weights": config.model_weights, "inference_image_size": config.inference_image_size,
              "configured_threshold": config.confidence_threshold, "by_threshold": {}}
    for threshold in sorted({*THRESHOLDS, config.confidence_threshold}):
        result = DetectionEvaluation(iou_threshold=args.iou)
        for f in labels.frames:
            preds = [p for p in predictions[f.frame_index] if p[1] >= threshold]
            result.per_frame[f.frame_index] = match_frame(preds, f.people, iou_threshold=args.iou)
        c = result.counts
        marker = "  <- configured" if threshold == config.confidence_threshold else ""
        p = f"{c.precision:.1%}" if c.precision is not None else "n/a"
        r = f"{c.recall:.1%}" if c.recall is not None else "n/a"
        print(f"  {threshold:>5.2f}  {c.true_positives:>4} {c.false_positives:>4} {c.false_negatives:>4}  {p:>9} {r:>7}{marker}")
        report["by_threshold"][f"{threshold:.2f}"] = result.as_dict()

    reports = config.data_dir / "eval" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = reports / f"{safe_name(args.video.stem)}_detection_{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export", help="export frames and a label template")
    p_export.add_argument("video", type=Path)
    p_export.add_argument("--count", type=int, default=20)
    p_export.add_argument("--force", action="store_true")
    p_run = sub.add_parser("run", help="evaluate detections against labels")
    p_run.add_argument("video", type=Path)
    p_run.add_argument("--labels", type=Path, required=True)
    p_run.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()
    return export(args) if args.command == "export" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
