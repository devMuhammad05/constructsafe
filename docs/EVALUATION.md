# Evaluation (PRD §13)

How ConstructSafe is measured, and where the results go. **No metric in this
project is assumed.** Every number below has to come from running these tools
on labelled construction footage.

## Test footage

Videos aren't committed (PRD §8). The clips are listed in
`scripts/fetch_test_footage.py`, and every file name starts with its source
and ID. Run the script with no flags to see what's present; add `--download`
to fetch missing clips into `data/videos/`.

| File | Source | Author | Size | Used for |
|---|---|---|---|---|
| `pexels_33769531_vladimir-srajber_heavy-machinery-activity_1280x720.mp4` | [Pexels 33769531](https://www.pexels.com/video/construction-site-with-heavy-machinery-activity-33769531/) | Vladimir Srajber | 69.9 MB | Fixed camera, 66 s, workers on foot around an excavator, loader and truck. Main zone-entry clip |
| `pexels_38817827_seyhmus-kino_demolition-excavator-worker_1280x720.mp4` | [Pexels 38817827](https://www.pexels.com/video/construction-site-with-heavy-machinery-and-worker-38817827/) | Şeyhmus Kino | 6.5 MB | Worker by a demolition excavator in dust. Occlusion and poor visibility |
| `pexels_36327811_erkan-avanoglu_piling-rig-excavator_1280x720.mp4` | [Pexels 36327811](https://www.pexels.com/video/construction-site-with-heavy-machinery-operation-36327811/) | Erkan Avanoğlu | 5.4 MB | Fixed camera, small distant worker near a piling rig. Small-object detection |
| `pexels_34521514_sergei-starostin_workers-foundation-excavator_1280x720.mp4` | [Pexels 34521514](https://www.pexels.com/video/construction-workers-building-foundation-at-site-34521514/) | Sergei Starostin | 16.9 MB | Moving camera, several workers near an excavator. Detection, and the moving-camera limitation |
| `pexels_34521508_sergei-starostin_excavator-digging_1280x720.mp4` | [Pexels 34521508](https://www.pexels.com/video/excavator-digging-at-construction-site-34521508/) | Sergei Starostin | 7.9 MB | Excavator, no workers. Equipment check and a no-alert scenario |

All clips use the [Pexels License](https://www.pexels.com/license/): free
to use, attribution appreciated but not required. They show identifiable
people, so keep them local and use them only to evaluate this tool.

Stock footage is a stand-in. Before relying on the system at a real site,
repeat the evaluation on footage from that site's own cameras.

## 1. Event precision, recall and alert latency

1. Draw the zone(s) for the clip. `scripts/monitor_zone.py <clip> --zone "..." --preview`
   helps you check the position.
2. Watch the clip and write `data/eval/labels/<clip>.events.json`. It lists
   the zones, plus one entry for each time a worker's feet visibly cross into
   a zone (format in `constructsafe/evaluation.py`). Note who labelled it.
3. Run:

   ```bash
   uv run python scripts/evaluate_events.py data/videos/<clip>.mp4 --labels data/eval/labels/<clip>.events.json
   ```

It processes the clip into a separate database (`data/eval/`), matches events
to labelled entries, and prints and saves the following:

- **Event precision:** matched events ÷ all events. False alarms lower it.
- **Event recall:** matched entries ÷ all labelled entries. Missed hazards lower it.
- **Alert latency:** event time − labelled entry time (mean, median, max).
- **Processing FPS:** processed frames per second, with model warm-up excluded.

An event matches an entry in the same zone if it fires between 0.5 s before
and 2.0 s after the entry (`--early-tolerance`, `--max-latency`). Each event
can match only one entry.

## 2. Detection precision and recall

```bash
uv run python scripts/evaluate_detection.py export data/videos/<clip>.mp4 --count 20
# label data/eval/labels/<clip>.detection.json: one normalised [x1, y1, x2, y2] box per person per frame
uv run python scripts/evaluate_detection.py run data/videos/<clip>.mp4 --labels data/eval/labels/<clip>.detection.json
```

A detection counts as correct when it overlaps a labelled box with IoU ≥ 0.5.
Results are given for several confidence thresholds.

Draw the boxes by hand. Don't start from the model's own detections: that
biases the labels towards what the model already finds.

## 3. Low-powered machines

Run the event evaluation again with `--stride 2`, `--stride 3` or
`--max-width 640`. Record the FPS gained and any recall or latency lost
(PRD §14).

## Results

*Not measured yet.* Fill this in from the reports in `data/eval/reports/`,
and mirror the headline numbers in `docs/ROADMAP.md`.

| Clip | Settings | Event P | Event R | Latency (mean / max) | FPS | Detection P / R (conf 0.35) | Labelled by |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
