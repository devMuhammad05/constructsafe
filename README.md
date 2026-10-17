# ConstructSafe

Computer vision monitoring of worker–heavy equipment danger zones in
construction-site video. ConstructSafe detects people with a pretrained YOLO
model, checks whether they enter a manually configured danger zone, and logs
**potential hazards requiring human review**.

> ConstructSafe is a review aid. It is not a substitute for trained safety
> personnel or site safety procedures, and it does not guarantee safety.

See [`docs/PRD.md`](docs/PRD.md) for the spec and
[`docs/ROADMAP.md`](docs/ROADMAP.md) for progress.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+ (developed on 3.13).

```bash
uv sync
```

This creates `.venv/` and installs Ultralytics, OpenCV, Streamlit and pytest.
The pretrained `yolo11n.pt` weights (~5 MB) download into `models/` on first
run.

## Usage (Phase 1)

Put videos in `data/videos/` (git-ignored). Supported types: `.mp4`, `.avi`,
`.mov`, `.mkv`.

Detect and annotate people. The output goes to `data/outputs/`:

```bash
uv run python scripts/detect_people.py data/videos/site.mp4
```

Options: `--conf 0.5` (confidence threshold), `--stride 2` (process every 2nd
frame), `--max-frames 100`. Images (`.jpg`, `.png`) also work.

Check whether the pretrained model recognises the site's equipment:

```bash
uv run python scripts/check_equipment.py data/videos/site.mp4 --samples 20
```

## Tests

```bash
uv run pytest
```

## Configuration

All tunable values (confidence threshold, frame stride, persistence frames,
storage paths, model weights) are in
[`constructsafe/config.py`](constructsafe/config.py). Override any of them with
an environment variable prefixed `CONSTRUCTSAFE_`, for example
`CONSTRUCTSAFE_CONFIDENCE_THRESHOLD=0.5` or `CONSTRUCTSAFE_FRAME_STRIDE=3`.

## Data and privacy

Footage, evidence images, the SQLite database, outputs and model weights stay
on this machine under `data/` and `models/`. Both are git-ignored. The app
detects the `person` class only. It does no facial recognition and doesn't
identify individual workers.

## Known limitations

- Detection uses image space only: danger zones and positions are pixels, not
  metres.
- COCO-pretrained YOLO has no excavator, crane or forklift class, so equipment
  is covered by a manually drawn zone rather than detected.
- Baseline speed is about 7 fps for `yolo11n` at 640 px on a 16-thread CPU
  (CPU-only PyTorch, measured on a sample clip). Raise `frame_stride` or lower
  `max_frame_width` on slower machines.
