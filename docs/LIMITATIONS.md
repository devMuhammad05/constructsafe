# Known limitations (PRD §15)

ConstructSafe flags **potential hazards for human review**. It is not a safety
system, and it does not replace trained safety personnel or site procedures.
The limitations below come from the design and from testing so far. Update
this file as evaluation finds more.

## Detection

- **Pretrained COCO model.** Workers are detected as the generic `person`
  class. The model has no excavator, crane, forklift or piling-rig class, so
  equipment isn't detected; danger zones are drawn by hand. On the Pexels
  test clips, excavators, rollers and dump trucks showed up only
  intermittently as low-confidence `truck`, a piling rig as `train`/`car`,
  and a demolition excavator not at all. Run `scripts/check_equipment.py`
  to see what the model recognises in a given clip.
- **Small or distant workers** are missed more often, especially after frames
  are downscaled (`max_frame_width`, `inference_image_size`).
- **Dust, rain, low light, glare and partial occlusion** reduce detection.
  Hysteresis tolerates a few missed frames, but a worker who stays hidden for
  longer than the exit persistence window is treated as gone.
- **False detections** (signs, mannequins, people on posters, workers in
  machine cabs) can trigger alerts. An operator inside a cab whose feet point
  falls inside the zone will raise an alert. *Seen on the Pexels 33769531
  clip:* the excavator operator in the cab triggered a `danger_zone_entry`.
- **Duplicate boxes on one person.** YOLO sometimes draws two overlapping
  boxes on the same worker, which made the zone count read 2 and logged a
  bogus `additional_worker_entry` (seen twice on Pexels 33769531).
  *Mitigated:* near-identical boxes are now suppressed
  (`duplicate_iou_threshold`, `duplicate_containment_threshold`). The
  trade-off: if two real workers stand almost exactly behind each other, they
  can be counted as one, and the second worker's
  `additional_worker_entry` would be missed. The first entry into an empty
  zone is never lost this way.

## Zones and positions

- **Image space only.** Zones are polygons on the camera image. There's no
  real-world distance and no depth: a worker *behind* the equipment can
  appear inside the zone, and one beside it can appear outside.
- **Feet point.** Membership uses the bottom-centre of the person box. If the
  legs are hidden, the box bottom sits at the obstruction and the point is
  wrong.
- **Fixed camera assumed.** Zones don't follow pans, zooms or a moving
  camera (handheld, drone, or a camera mounted on the machine). Footage from a
  moving camera gives meaningless zone results.
- **Equipment moves, zones don't.** A zone around a slewing or tracking
  machine must cover its whole working area, or it will miss entries.

## Events

- **Count-based, no tracking.** Each zone keeps a worker count rather than
  person IDs. If one worker leaves just as another enters (within the
  persistence window), the swap may not register as a new entry.
- **Latency by design.** An entry is confirmed on the
  `enter_persistence_frames`-th consecutive processed frame inside the zone.
  With the defaults (3 frames, stride 1) that's about 0.07 s at 30 fps, and
  it grows with the frame stride. A dash into the zone shorter than that
  isn't reported.
- **Clearing.** After a count drop the warning can take up to twice
  `exit_persistence_frames` to clear fully.
- **Workers on the zone boundary.** Hysteresis is in time only. A worker
  standing right on the zone edge can drift in and out and trigger repeated
  `danger_zone_entry` alerts (seen in a UI test, 2.7 s apart).
- **Frame stride trades latency and coverage for speed.** At stride 2,
  persistence windows cover twice the video time, and brief events, including
  false alarms, can fall between sampled frames. So results at different
  strides aren't directly comparable.

## Performance

- CPU-only inference: 8.3–9.7 processed frames/s for `yolo11n` at 640 px
  on a 16-thread laptop CPU, on the 1280×720 test clips. That's below the
  30 fps source rate, so a 1-minute clip takes about 3–4 minutes at stride 1.
  Raise the frame stride to process faster.
- Processing in the Streamlit app is synchronous: it blocks that browser
  session until it finishes. It's also slower than the command line (5.4 vs
  9.0 fps on the same clip) because of the live preview.

## User interface

- Zones are set with sliders or typed points; you can't draw them by
  clicking on the frame.
- In narrow windows, long video file names and some labels in the events
  table and filters are cut off.
- Only one video is processed at a time, with no queue or background
  processing.

## Privacy and deployment

- The app has no login and serves on localhost only. Before any real-site or
  network deployment it needs access control, and a `/security-review`.
- Evidence screenshots show identifiable workers. They are stored locally
  with no automatic deletion; set a retention policy before real use.

## Evaluation

- Test footage is stock video, not footage from the site where the tool
  would run. Results don't transfer automatically to other cameras, angles or
  lighting.
- Ground-truth labels are drawn by hand, and their quality limits how far the
  metrics can be trusted.
