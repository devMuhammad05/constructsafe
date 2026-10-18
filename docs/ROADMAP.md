# Roadmap and Progress Tracker

Tracks the MVP work from `docs/PRD.md`. Update the status of an item when it
changes, and add a short note or link (commit or PR) when useful.

**Legend:** ✅ Done · 🟡 Partially done · ⬜ Not started

**Last updated:** 2026-10-18

## Summary

| Phase | Status |
|---|---|
| 0. Project setup | ✅ Done |
| 1. Object detection | ✅ Done |
| 2. Danger-zone logic | ✅ Done |
| 3. Event logging | ✅ Done |
| 4. Dashboard | ✅ Done |
| 5. Testing and demonstration | 🟡 Partially done |
| 6. ~~Live monitoring~~ | Removed from scope (2026-10-17) |
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
| ✅ | Test whether pretrained YOLO detects the target equipment, and record the result | §14 · On the 5 Pexels clips (12 sampled frames each, conf ≥ 0.25): no excavator class exists; excavators, rollers and dump trucks appear only intermittently as low-confidence `truck` (≈0.25–0.5), a piling rig as `train`/`car`, and a demolition excavator not at all. Junk labels (giraffe, bench) appear on machinery. **Conclusion: pretrained YOLO can't locate equipment reliably; keep manually drawn zones.** |
| ✅ | Run person detection on real construction footage | FR-02 · all 5 Pexels clips processed (stride 2). Spot-checked: workers found in dust, at distance and near machines; 0 people in the excavator-only clip. Accuracy not yet measured (Phase 5) |
| ✅ | Record baseline CPU speed | 8.3–9.7 processed fps on 1280×720 site clips (`yolo11n`, 640 px inference, 16-thread CPU, detection + annotation + writing). Earlier sample clip: ~7–8 fps |

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
| ✅ | Upload page with file-type and readability checks | FR-01 · `uploads.py` + `app/views/process.py`; invalid files rejected with a clear error and not kept. Valid upload covered by unit tests; invalid upload checked in the browser |
| ✅ | Zone configuration UI | FR-03 · rectangle sliders or polygon points (%), live preview on the first frame, saved per video. Fixed: zone name no longer clears after a save (re-saving created a duplicate zone); Delete buttons no longer squashed |
| ✅ | Processing status: pending, processing, completed or failed, with retry | FR-08 · live progress and preview; `Processing runs` page with errors and Retry; runs interrupted by an app stop are marked failed on start-up |
| ✅ | Show annotated footage | FR-05 · browser-playable output (`video_out.py`: H.264 MP4, else VP8 WebM) |
| ✅ | Event history: count, list, timestamp and evidence image | FR-07 · `Safety events` page: metrics, filters, table, evidence |
| ✅ | Mark events as reviewed and tell new events apart from reviewed ones | FR-07 |
| ✅ | Label alerts as potential hazards requiring human review | §8 Safety · sidebar notice, events page banner, stored description, banner on frames |
| ✅ | Serve the app on localhost only, no usage telemetry | §8 Privacy · `.streamlit/config.toml` |

## Phase 5 — Testing and demonstration

| Status | Task | PRD ref |
|---|---|---|
| ✅ | Unit tests for zone geometry, the event state machine and storage | §13 · 73 tests incl. storage, evidence paths and pipeline failure handling |
| 🟡 | Scenario: worker outside the zone | §13 · unit-tested with synthetic detections; real footage pending |
| 🟡 | Scenario: worker entering, staying inside and leaving the zone | §13 · unit-tested; entry verified on a sample clip; real footage pending |
| 🟡 | Scenario: several workers near the equipment | §13 · unit-tested (`additional_worker_entry`); real footage pending |
| 🟡 | Scenario: occlusion or missed detections, and objects leaving the frame | §13 · unit-tested; real footage pending |
| ⬜ | Measure detection precision and recall | §13 · tool ready: `scripts/evaluate_detection.py` (export frames → hand-label → run). Needs labels |
| 🟡 | Measure event precision and recall | §13 · first clip (33769531, 1 labelled entry): recall 1/1; precision 1/4 → 1/2 after duplicate suppression (stride 1). See `docs/EVALUATION.md`. Needs more clips/entries before the numbers mean anything |
| 🟡 | Measure processing FPS and alert latency | §13 · 9.0 fps CLI / 5.4 fps UI at 1280×720; latency 0.0 s (stride 1), 0.1 s (stride 2) on 1 entry. Stride/width sweep not done |
| ✅ | Suppress duplicate person boxes | `detection.suppress_duplicates`; thresholds from measured duplicates; removed 2 of 3 false alarms on 33769531 |
| ⬜ | Exclusion areas inside zones (e.g. machine cabs) | Remaining false alarm on 33769531 is the excavator operator |
| 🟡 | Document test results and known limitations | §15 · `docs/LIMITATIONS.md` written; results table in `docs/EVALUATION.md` still empty |
| 🟡 | Prepare an end-to-end demonstration | §15 · `docs/DEMO.md` script + `scripts/reset_demo.py`; not yet rehearsed on site footage |
| ✅ | Evaluation tooling with unit tests | `constructsafe/evaluation.py`: one-to-one event matching with latency, IoU detection matching, label loaders |
| ✅ | Source test footage | 5 Pexels clips (106.7 MB) downloaded to `data/videos/`, listed in `scripts/fetch_test_footage.py` / `docs/EVALUATION.md` (file names carry source + ID) |

## Phase 6 — Live monitoring (removed)

Removed from scope on 2026-10-17 at the product owner's request. ConstructSafe
processes uploaded, recorded videos only. See PRD v1.1.

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

- [x] A user can upload and process a supported construction video
- [ ] The system detects workers in the footage
- [x] Entering a configured danger zone triggers a visible potential-hazard warning
- [x] The system records the event timestamp and an evidence screenshot
- [x] The dashboard shows recorded events
- [x] Invalid input and processing failures are handled gracefully
- [ ] Test results and known limitations are documented
- [ ] The app can be demonstrated end to end on a development computer
