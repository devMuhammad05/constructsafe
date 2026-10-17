# End-to-end demo (PRD §15)

A short run-through showing every Definition of Done item. It takes about 10
minutes on a development laptop. No special camera hardware is needed.

## Before the demo

```bash
uv sync
uv run python scripts/fetch_test_footage.py --download   # if the clips aren't in data/videos/ yet
uv run python scripts/reset_demo.py --yes                # optional: start with an empty event history
uv run streamlit run app/main.py
```

Open <http://localhost:8501>. Load the model once beforehand (process any
short clip), so the first demo run doesn't pause on model loading.

## Script

1. **Safety framing.** Point out the sidebar notice: alerts are *potential
   hazards requiring human review*, and the tool doesn't replace safety staff.
2. **Invalid input (DoD 6).** Upload a non-video file renamed to `.mp4`. It
   is rejected with a clear error.
3. **Upload (DoD 1).** Upload or pick
   `pexels_33769531_vladimir-srajber_heavy-machinery-activity_1280x720.mp4`.
4. **Zone (DoD 3).** Draw a rectangle around the excavator's working area
   with the sliders. Show the live preview, then **Save zone**.
5. **Process (DoD 1, 2).** Press **Process video**. Show the progress bar,
   the live preview with person boxes, and the run status.
6. **Warning (DoD 3).** In the annotated video, show the zone turning red,
   the in-zone worker highlighted, and the banner with event type and
   timestamp.
7. **Evidence and history (DoD 4, 5).** Open **Safety events**. Show the
   counts, select an event, show its timestamp and evidence screenshot, and
   mark it reviewed. The new and reviewed counts update.
8. **Failure handling (DoD 6).** Open **Processing runs**. Show a failed run's
   error message and **Retry**.
9. **Results and limits (DoD 7).** Show `docs/EVALUATION.md` (measured
   metrics) and `docs/LIMITATIONS.md`.

## After the demo

`uv run python scripts/reset_demo.py --yes` clears the database, evidence and
outputs. Videos and evaluation data are kept.
