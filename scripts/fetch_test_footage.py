"""Download the evaluation clips listed in MANIFEST into data/videos/.

Videos are never committed (PRD §8), so this script makes the test set reproducible.
Each file name starts with its source and ID, so its origin is always visible.

    uv run python scripts/fetch_test_footage.py            # list clips and sizes, download nothing
    uv run python scripts/fetch_test_footage.py --download # download clips that aren't present yet

All clips are from Pexels under the Pexels License (https://www.pexels.com/license/):
free to use, attribution not required but credited here. The footage shows identifiable
people, so keep it local and use it only for evaluating this tool.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from constructsafe.config import load_config


@dataclass(frozen=True)
class Clip:
    filename: str
    url: str
    page: str
    author: str
    size_bytes: int
    purpose: str


MANIFEST = (
    Clip(
        "pexels_33769531_vladimir-srajber_heavy-machinery-activity_1280x720.mp4",
        "https://videos.pexels.com/video-files/33769531/14335306_1280_720_30fps.mp4",
        "https://www.pexels.com/video/construction-site-with-heavy-machinery-activity-33769531/",
        "Vladimir Srajber",
        69_917_142,
        "Fixed camera, 66 s: workers on foot around an excavator, loader and truck. Main zone-entry scenario clip.",
    ),
    Clip(
        "pexels_38817827_seyhmus-kino_demolition-excavator-worker_1280x720.mp4",
        "https://videos.pexels.com/video-files/38817827/16500098_1280_720_30fps.mp4",
        "https://www.pexels.com/video/construction-site-with-heavy-machinery-and-worker-38817827/",
        "Şeyhmus Kino",
        6_502_645,
        "16 s: worker beside a demolition excavator in dust. Occlusion / poor visibility.",
    ),
    Clip(
        "pexels_36327811_erkan-avanoglu_piling-rig-excavator_1280x720.mp4",
        "https://videos.pexels.com/video-files/36327811/15406631_1280_720_30fps.mp4",
        "https://www.pexels.com/video/construction-site-with-heavy-machinery-operation-36327811/",
        "Erkan Avanoğlu",
        5_422_847,
        "Fixed camera, 11 s: small, distant worker near a piling rig and excavator. Small-object detection.",
    ),
    Clip(
        "pexels_34521514_sergei-starostin_workers-foundation-excavator_1280x720.mp4",
        "https://videos.pexels.com/video-files/34521514/14626368_1280_720_30fps.mp4",
        "https://www.pexels.com/video/construction-workers-building-foundation-at-site-34521514/",
        "Sergei Starostin",
        16_917_662,
        "Moving camera, 20 s: several workers close to an excavator. Detection; shows the moving-camera limitation for zones.",
    ),
    Clip(
        "pexels_34521508_sergei-starostin_excavator-digging_1280x720.mp4",
        "https://videos.pexels.com/video-files/34521508/14626352_1280_720_30fps.mp4",
        "https://www.pexels.com/video/excavator-digging-at-construction-site-34521508/",
        "Sergei Starostin",
        7_917_656,
        "15 s: excavator with no workers. Equipment check, and a no-worker (no-alert) scenario.",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="download missing clips")
    args = parser.parse_args()

    videos_dir = load_config().videos_dir
    videos_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for clip in MANIFEST:
        target = videos_dir / clip.filename
        present = target.is_file() and target.stat().st_size == clip.size_bytes
        total += clip.size_bytes
        print(f"{'present ' if present else 'missing '} {clip.size_bytes / 1e6:6.1f} MB  {clip.filename}")
        if present or not args.download:
            continue
        partial = target.with_name(target.name + ".download")
        request = urllib.request.Request(clip.url, headers={"User-Agent": "ConstructSafe-eval/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            print(f"  error: {exc}", file=sys.stderr)
            return 1
        if partial.stat().st_size != clip.size_bytes:
            partial.unlink(missing_ok=True)
            print(f"  error: size mismatch for {clip.filename}; not saved", file=sys.stderr)
            return 1
        partial.replace(target)
        print("  downloaded")
    print(f"total {total / 1e6:.1f} MB in {videos_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
