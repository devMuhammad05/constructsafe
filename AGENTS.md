# AGENTS.md

Guidance for AI coding agents (Codex, Cursor, Copilot, Claude Code and others) working in this repository.

## Project

**ConstructSafe** is a computer vision safety-monitoring web app. It detects
workers in construction-site video, checks whether they enter a user-defined
danger zone around heavy equipment, shows visual warnings, and logs
potential-hazard events (timestamp + evidence screenshot) for review on a
dashboard.

The full spec is in `docs/PRD.md`, and progress is tracked in
`docs/ROADMAP.md`. Read it before you make product or scope
decisions. If a request conflicts with the PRD, point out the conflict rather
than quietly departing from it.

**Status:** Phase 0 done; Phase 1 (person detection) mostly done. Keep this
file in step with the code, dependencies and commands.

## Commands

```bash
uv sync                                              # install / update the environment
uv run pytest                                        # unit tests (no YOLO or real video needed)
uv run python scripts/detect_people.py <video|image> # annotate people -> data/outputs/
uv run python scripts/check_equipment.py <video>     # which COCO classes does YOLO see?
```

Python: the project uses the system Python 3.13 (`.python-version`). Don't
let uv download a managed Python from inside the Claude desktop app: its
sandbox redirects `%APPDATA%`, so the install is invisible outside the app.

## Tech stack (PRD §9)

| Concern | Choice |
|---|---|
| Language | Python |
| Object detection | Ultralytics YOLO with **pretrained weights** (no custom training unless testing shows it's needed) |
| Video I/O and drawing | OpenCV |
| UI | Streamlit |
| Event storage | SQLite |
| Evidence images | Local file storage |
| Package and environment management | **uv** (`pyproject.toml` + `uv.lock`) |

Don't add frameworks, services, cloud dependencies or extra databases beyond
this list without asking first. The one approved optional addition is a
locally run Gemma 4 model for event review (see the Gemma 4 section below).

## Package management (uv)

Use [uv](https://docs.astral.sh/uv/) for every Python dependency and
environment task. Don't use `pip`, `pip-tools`, `poetry`, `conda` or a
hand-made `venv`, and don't add a `requirements.txt`.

- Dependencies live in `pyproject.toml`; commit `uv.lock` alongside it.
- Add a dependency: `uv add <package>` (dev-only: `uv add --dev <package>`).
  Remove one with `uv remove <package>`.
- Install/sync the environment: `uv sync` (creates `.venv/`, which is
  git-ignored).
- Run anything inside the project environment with `uv run`, e.g.
  `uv run pytest`, `uv run streamlit run app/main.py`.
- Pin the Python version with `uv python pin` (writes `.python-version`).

## Architecture

Pipeline (PRD §10):

```
Video input → Frame extraction → Object detection → Danger-zone evaluation
  → Event generation → Evidence capture → Database storage → Dashboard
```

**Key rule:** keep the detection/processing pipeline independent of Streamlit.
The core modules must not import `streamlit`. The pipeline should take a
generic frame source, so that a live camera stream (Phase 6) can replace
uploaded video files without a rewrite.

Suggested layout (adjust as the code takes shape, then update this section):

```
app/                 # Streamlit UI only (upload, processing status, dashboard) - Phase 4
constructsafe/
  config.py          # all tunables + storage paths; CONSTRUCTSAFE_* env overrides  [exists]
  sources.py         # frame sources: video file now, camera later  [exists]
  detection.py       # YOLO wrapper → person detections (bbox, label, confidence)  [exists]
  zones.py           # danger-zone polygons + point-in-zone checks
  events.py          # zone-entry state machine, duplicate suppression
  evidence.py        # screenshot capture to local storage
  storage.py         # SQLite access for SafetyEvent and zone configs
  annotate.py        # draw boxes, zone overlay, warning banners  [boxes exist]
  pipeline.py        # glues the stages together; reports progress/status
  review.py          # optional Gemma 4 review of event frames (off by default)
scripts/             # CLI tools for development and evaluation  [exists]
tests/
data/                # local videos, evidence images, sqlite db, outputs (git-ignored)
models/              # YOLO weights, downloaded on first run (git-ignored)
docs/
```

## Gemma 4 vision-language review (optional, post-MVP)

Gemma 4 (Google, open weights, Apache 2.0) is an **optional second-pass
reviewer**. It is not part of the PRD's core stack and does not replace YOLO.
Build it only after Phases 1–4 work. Track it as Phase 7 in `docs/ROADMAP.md`.

**Use it for:**
- Reviewing the evidence screenshot of each zone-entry event, e.g. "Is a
  person close to heavy machinery? yes / no / unsure".
- Identifying the equipment type in a frame (excavator, dump truck, forklift…)
  to label zones, and checking early whether YOLO's pretrained weights cover
  the target equipment.
- Writing a one-sentence description of each event for the dashboard.
- Summarising a processed video's events into a short report.

**Rules:**
- Run it **only on frames that already produced an event**, never on every
  frame. YOLO does per-frame detection; Gemma 4 is far too slow for that.
- Its output is supporting information. It must **never suppress, delete or
  downgrade an event**: a missed hazard is worse than a false alarm.
- Run it **locally** (Ollama or Hugging Face Transformers) so footage stays on
  the machine. Don't send site footage to a cloud API without explicit
  approval.
- Start with the E4B model on a laptop. Use 26B A4B or 31B only when a capable
  GPU is available. Keep the model name configurable.
- Keep it in its own module (`constructsafe/review.py`). Turn it off by
  default with a config flag. The pipeline must work unchanged when it's off,
  or when the model isn't installed or fails.
- Ask for structured JSON (e.g. `{"person_near_equipment": "yes|no|unsure",
  "equipment_type": "...", "confidence": 0.0}`), validate it, and store it as
  extra fields on the event.
- Label its output in the UI as **"AI-generated, requires human review"**.
- Don't prompt it to describe, identify or recognise individual people. The
  PRD's privacy rules apply.
- Before relying on it, measure whether it actually reduces false alarms on
  the test videos, and record the result in the roadmap.

## Domain rules

- **Workers:** detect the COCO `person` class. Show a bounding box, label and
  confidence for each one. Filter detections below a configurable confidence
  threshold.
- **Equipment:** in the MVP the danger zone is a **manually configured polygon
  in image space**, tied to a video or camera view. Pretrained YOLO may not
  recognise excavators, so a manual zone is the fallback, not optional extra
  work.
- **Zone membership:** check a worker's position against the polygon. The
  bottom-centre of the bbox (the feet) is a sensible default; whatever you
  choose, document it. Don't compute or claim real-world distances in metres.
- **Events (FR-04, FR-06):**
  - Emit one event when a worker *enters* the zone, not one per frame while
    they stay inside.
  - Clear the warning when the interaction ends. Use temporal persistence or
    hysteresis (e.g. N frames in or out) so flickering detections don't cause
    alert spam or missed exits.
  - Handle missing detections and occlusion without crashing.
- **Processing status (FR-08):** each video is `pending`, `processing`,
  `completed` or `failed`. A failure needs a useful error message and a retry
  option.
- **Upload validation (FR-01):** check the file type and readability before
  processing. Show a clear error for invalid files.

## Data model (PRD §11)

`SafetyEvent`: `id`, `source_name`, `timestamp_seconds` (position in the
video), `event_type`, `zone_id` (nullable), `evidence_path`, `review_status`
(at minimum new vs. reviewed), `created_at`.

Store danger-zone configs separately: name, polygon coordinates, and the
associated video/camera identifier.

## Non-negotiables

- **Safety wording:** label every alert in the UI and in stored data as a
  *potential hazard requiring human review*. Never present the app as a
  substitute for safety personnel, and never claim certified or guaranteed
  safety.
- **Privacy:** no facial recognition, no identification of individual workers,
  and no extra personal data. Keep footage and evidence only in the configured
  local storage location. Never commit videos, evidence images or database
  files.
- **Out of scope for the MVP** (don't build without asking): PPE/helmet/vest
  detection, multi-camera tracking, mobile apps, cloud deployment, automatic
  equipment stop or emergency controls, physical distance estimation.

## Roadmap (PRD §12)

1. Object detection: environment set up, detect and annotate people, test
   whether equipment is detectable.
2. Danger-zone logic: zone configuration, entry checks, warning states,
   duplicate suppression.
3. Event logging: evidence screenshots, SQLite persistence.
4. Dashboard: upload, annotated footage, processing status, event history.
5. Testing and demo: see the evaluation section below.
6. Optional: live webcam/camera stream.
7. Optional: Gemma 4 review of event frames (see the Gemma 4 section above).

Work in phase order unless asked otherwise.

### Progress tracking

`docs/ROADMAP.md` is the source of truth for what is done, partially done or
not started.

- Check it at the start of a task to see what already exists and what comes
  next.
- When you finish or partly finish a task, update its status in the same
  commit (✅ done, 🟡 partially done, ⬜ not started). Add a short note on what
  remains for a 🟡 item, update the phase summary table and the
  "Last updated" date, and tick the Definition of Done items that are met.
- If you do work the roadmap doesn't list, add a row to the right phase rather
  than leaving it untracked.

## Testing and evaluation (PRD §13)

- Unit-test the pure logic (zone geometry, the event state machine, duplicate
  suppression, storage) without loading YOLO or real video. Use synthetic
  detections.
- Scenario coverage: worker outside the zone, entering, staying inside,
  leaving, several workers, occlusion or missed detections, objects leaving
  the frame.
- Metrics to measure and document (don't assume them): detection
  precision/recall, event precision/recall, processing FPS, alert latency.
- Performance on low-powered machines: reduce input resolution or frame
  stride, and measure the effect on quality.

## Conventions

- Keep configuration (confidence threshold, frame stride, persistence frames,
  storage paths, model weights) in one config module or file. Don't hardcode
  these values in the pipeline code.
- Keep model weights, sample videos and generated outputs out of git. Add them
  to `.gitignore` when the project is scaffolded.
- Write down known limitations as you find them (image-space zones, occlusion,
  equipment that isn't recognised). Documenting limitations is part of the
  Definition of Done (PRD §15).
