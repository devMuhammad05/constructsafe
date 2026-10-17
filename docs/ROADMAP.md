# Roadmap and Progress Tracker

Tracks the MVP work from `docs/PRD.md`. Update the status of an item when it
changes, and add a short note or link (commit or PR) when useful.

**Legend:** ✅ Done · 🟡 Partially done · ⬜ Not started

**Last updated:** 2026-10-17

## Summary

| Phase | Status |
|---|---|
| 0. Project setup | ✅ Done |
| 1. Object detection | 🟡 Partially done |
| 2. Danger-zone logic | ✅ Done |
| 3. Event logging | ✅ Done |
| 4. Dashboard | 🟡 Partially done |
| 5. Testing and demonstration | 🟡 Partially done |
| 6. Optional live monitoring | ⬜ Not started |
| 7. Optional Gemma 4 event review | ⬜ Not started |

## Phase 0 — Project setup

| Status | Task | Notes |
|---|---|---|
| ✅ | Write the PRD | `docs/PRD.md` |
| ✅ | Add agent guidance files | `CLAUDE.md`, `AGENTS.md` |
| ✅ | Create this roadmap | `docs/ROADMAP.md` |
| ✅ | Choose uv as the package and environment manager | uv 0.13.1 installed; rules in `CLAUDE.md` / `AGENTS.md` |
| ✅ | Set up the Python environment with uv (`pyproject.toml`, `uv.lock`) | Python 3.13 (system), CPU PyTorch |
| ✅ | Scaffold the package layout and `tests/` | `constructsafe/`, `scripts/`, `tests/`; `app/` comes in Phase 4 |
| ✅ | Add `.gitignore` for videos, evidence, weights, the database and `.venv/` | |
| ✅ | Add a central config (threshold, frame stride, persistence frames, paths) | `constructsafe/config.py`, `CONSTRUCTSAFE_*` env overrides |
| ✅ | Add a README with setup and run instructions | `README.md` |

## Phase 1 — Object detection

| Status | Task | PRD ref |
|---|---|---|
| ✅ | Load a video as a frame source, with file-type and readability checks | FR-01 · `sources.py` |
| ✅ | Run pretrained YOLO and keep only `person` detections | FR-02 · `detection.py`, `yolo11n.pt` |
| ✅ | Draw bounding boxes with label and confidence | FR-02 · `annotate.py`, `scripts/detect_people.py` |
| ✅ | Filter detections by a configurable confidence threshold | FR-02 · default 0.35 |
| 🟡 | Test whether pretrained YOLO detects the target equipment, and record the result | §14 · `scripts/check_equipment.py` works (tested on a sample street image only). Still needs real construction footage |
| 🟡 | Run person detection on real construction footage | FR-02 · verified only on Ultralytics' sample image and a synthetic clip; no site video in the repo yet |
| ✅ | Record baseline CPU speed | ~7–8 fps, `yolo11n` at 640 px, 16-thread CPU, after warm-up, including annotation and logging |

## Phase 2 — Danger-zone logic

| Status | Task | PRD ref |
|---|---|---|
| ✅ | Define a danger-zone polygon per video or camera view | FR-03 · `zones.py`; normalised 0–1 coords, `--zone` or JSON file, `source_name` ties a zone to a video. SQLite storage in Phase 3, UI in Phase 4 |
| ✅ | Draw the zone as an overlay on frames | FR-03 · amber when idle, red when occupied |
| ✅ | Check worker positions against the zone (bbox bottom-centre) | FR-03 · boundary counts as inside |
| ✅ | Add enter/inside/exit warning states | FR-04 · `events.py`, per-zone worker count with hysteresis |
| ✅ | Suppress duplicate alerts and debounce flickering detections | FR-04 · enter 3 / exit 5 processed frames (config). No tracker, so ID switches can't duplicate alerts |
| ✅ | Show a visible "potential hazard" warning in annotated footage | FR-05 · red banner with event type, zone and timestamp; in-zone workers in red |
| ✅ | Pipeline glue and zone-monitor CLI | `pipeline.py` (no Streamlit), `scripts/monitor_zone.py` → annotated video + events JSON |

## Phase 3 — Event logging

| Status | Task | PRD ref |
|---|---|---|
| ✅ | Create the SQLite schema for `SafetyEvent` and zone configs | §11 · `storage.py`: `safety_events`, `danger_zones`, `processing_runs`; schema versioned via `PRAGMA user_version` |
| ✅ | Save evidence screenshots to local storage | FR-06 · `evidence.py`: annotated frame as JPEG in `data/evidence/`; sanitised names, relative paths, traversal-checked |
| ✅ | Record events with timestamp, type, zone, evidence path and review status | FR-06 · plus run id, frame, first-seen time, worker count and the "requires human review" description. An event is kept even if its screenshot fails |
| ✅ | Verify events persist across app restarts | FR-06 · unit test reopens the DB; verified on the sample clip (zones reloaded from DB on second run) |
| ✅ | End-to-end `process_video()` with run status and error capture | `pipeline.py`; `scripts/monitor_zone.py` uses it |

## Phase 4 — Dashboard (Streamlit)

| Status | Task | PRD ref |
|---|---|---|
| ⬜ | Upload page with file-type and readability checks | FR-01 |
| ⬜ | Zone configuration UI | FR-03 |
| 🟡 | Processing status: pending, processing, completed or failed, with retry | FR-08 · stored per run with error messages; a retry is a new run. UI still to build |
| ⬜ | Show annotated footage | FR-05 |
| ⬜ | Event history: count, list, timestamp and evidence image | FR-07 |
| ⬜ | Mark events as reviewed and tell new events apart from reviewed ones | FR-07 |
| ⬜ | Label alerts as potential hazards requiring human review | §8 Safety |

## Phase 5 — Testing and demonstration

| Status | Task | PRD ref |
|---|---|---|
| ✅ | Unit tests for zone geometry, the event state machine and storage | §13 · 73 tests incl. storage, evidence paths and pipeline failure handling |
| 🟡 | Scenario: worker outside the zone | §13 · unit-tested with synthetic detections; real footage pending |
| 🟡 | Scenario: worker entering, staying inside and leaving the zone | §13 · unit-tested; entry verified on a sample clip; real footage pending |
| 🟡 | Scenario: several workers near the equipment | §13 · unit-tested (`additional_worker_entry`); real footage pending |
| 🟡 | Scenario: occlusion or missed detections, and objects leaving the frame | §13 · unit-tested; real footage pending |
| ⬜ | Measure detection precision and recall | §13 |
| ⬜ | Measure event precision and recall | §13 |
| ⬜ | Measure processing FPS and alert latency | §13 |
| ⬜ | Document test results and known limitations | §15 |
| ⬜ | Prepare an end-to-end demonstration | §15 |

## Phase 6 — Optional live monitoring

| Status | Task | PRD ref |
|---|---|---|
| ⬜ | Connect a webcam or camera stream as a frame source | §12 |
| ⬜ | Evaluate frame rate and detection latency | §12 |
| ⬜ | Test under different lighting and camera angles | §12 |

## Phase 7 — Optional Gemma 4 event review

Post-MVP. Start only after Phases 1–4 work. See the Gemma 4 section in
`CLAUDE.md` / `AGENTS.md` for the rules.

| Status | Task | Notes |
|---|---|---|
| ⬜ | Set up a local Gemma 4 runtime (Ollama or Transformers), starting with E4B | Model name configurable |
| ⬜ | Add `constructsafe/review.py` behind a config flag that is off by default | Pipeline works without it |
| ⬜ | Review event screenshots with a structured JSON prompt and validate the output | Only frames with events |
| ⬜ | Store review results as extra fields on `SafetyEvent` | Never suppresses events |
| ⬜ | Identify equipment type to help label zones | Supports the §14 equipment risk |
| ⬜ | Show an event description and an "AI-generated, requires human review" label in the dashboard | |
| ⬜ | Generate a per-video event summary | |
| ⬜ | Handle a missing model, timeouts and invalid output gracefully | |
| ⬜ | Measure the effect on false alarms and processing time, and document the results | Decide whether to keep it |

## MVP Definition of Done (PRD §15)

- [ ] A user can upload and process a supported construction video
- [ ] The system detects workers in the footage
- [x] Entering a configured danger zone triggers a visible potential-hazard warning
- [x] The system records the event timestamp and an evidence screenshot
- [ ] The dashboard shows recorded events
- [ ] Invalid input and processing failures are handled gracefully
- [ ] Test results and known limitations are documented
- [ ] The app can be demonstrated end to end on a development computer
