"""Upload a video, configure its danger zone(s) and process it (FR-01, FR-03, FR-08)."""

from __future__ import annotations

import streamlit as st

from constructsafe.annotate import draw_zones
from constructsafe.evidence import safe_name
from constructsafe.sources import VideoValidationError
from constructsafe.storage import STATUS_COMPLETED, STATUS_FAILED
from constructsafe.uploads import list_videos, resolve_video, save_upload
from constructsafe.zones import DangerZone, ZoneConfigError
from ui_common import (
    STATUS_BADGES,
    bgr_to_rgb,
    first_frame,
    format_time,
    get_config,
    get_storage,
    rgb_to_bgr,
    run_processing,
    show_video,
)

config = get_config()
storage = get_storage()

st.header("Process a construction-site video")

# --- 1. Video -----------------------------------------------------------------

st.subheader("1. Choose a video")
upload_col, pick_col = st.columns(2)
with upload_col:
    uploaded = st.file_uploader(
        "Upload a video",
        type=[ext.lstrip(".") for ext in config.allowed_video_extensions],
        help="Footage is stored only on this computer, in the local data folder.",
    )
    if uploaded is not None and st.session_state.get("last_upload_id") != uploaded.file_id:
        st.session_state["last_upload_id"] = uploaded.file_id
        try:
            with st.spinner("Checking the video…"):
                info = save_upload(uploaded.getvalue(), uploaded.name, config)
        except VideoValidationError as exc:
            st.session_state.pop("video_name", None)
            st.session_state["upload_error"] = str(exc)
        else:
            st.session_state.pop("upload_error", None)
            st.session_state["video_name"] = info.path.name
            st.session_state["upload_ok"] = (
                f"Uploaded **{info.path.name}**: {info.width}×{info.height}, "
                f"{info.fps:.1f} fps, {format_time(info.duration_seconds)} long."
            )
    if "upload_error" in st.session_state:
        st.error(st.session_state["upload_error"], icon=":material/error:")
    elif "upload_ok" in st.session_state:
        st.success(st.session_state["upload_ok"], icon=":material/check_circle:")

with pick_col:
    videos = [p.name for p in list_videos(config)]
    if videos:
        current = st.session_state.get("video_name")
        choice = st.selectbox(
            "…or pick a video already stored",
            videos,
            index=videos.index(current) if current in videos else None,
            placeholder="Select a video",
        )
        if choice and choice != current:
            st.session_state["video_name"] = choice
            st.session_state.pop("upload_ok", None)
            st.session_state.pop("upload_error", None)
            st.rerun()
    else:
        st.caption("No stored videos yet.")

video_name = st.session_state.get("video_name")
if not video_name:
    st.info("Upload or select a video to continue.")
    st.stop()

try:
    video_path = resolve_video(config, video_name)
    if not video_path.is_file():
        raise VideoValidationError(f"{video_name} is no longer in local storage.")
    frame_rgb = first_frame(str(video_path), video_path.stat().st_mtime, config.max_frame_width)
except VideoValidationError as exc:
    st.error(str(exc))
    st.session_state.pop("video_name", None)
    st.stop()

# --- 2. Danger zones ----------------------------------------------------------

st.subheader(f"2. Danger zones for {video_name}")
st.caption(
    "Mark the area around the equipment where workers shouldn't be. A worker counts as inside "
    "when the bottom of their box (their feet) is in the zone. Zones are image regions, not "
    "real-world distances."
)

zones = storage.list_zones(video_name)
height, width = frame_rgb.shape[:2]

editor_col, preview_col = st.columns([2, 3])
with editor_col:
    with st.container(border=True):
        zone_name = st.text_input("Zone name", value="Excavator swing area" if not zones else "")
        mode = st.radio("Shape", ["Rectangle", "Polygon points"], horizontal=True)
        st.caption("Positions are percentages of the frame: 0 is left/top, 100 is right/bottom.")
        if mode == "Rectangle":
            x_range = st.slider("Left → right (%)", 0, 100, (40, 90))
            y_range = st.slider("Top → bottom (%)", 0, 100, (50, 100))
        else:
            points_text = st.text_area(
                "Polygon points: one `x%, y%` pair per line, at least 3",
                value="40, 50\n90, 50\n100, 100\n30, 100",
                height=130,
            )
        submitted = st.button("Save zone", type="primary", icon=":material/save:")

    draft = None
    error = None
    try:
        if mode == "Rectangle":
            (x1, x2), (y1, y2) = x_range, y_range
            if x1 == x2 or y1 == y2:
                raise ZoneConfigError("The rectangle needs a non-zero width and height.")
            pts = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
        else:
            pts = tuple(
                tuple(float(v) for v in line.replace(";", ",").split(","))
                for line in points_text.splitlines()
                if line.strip()
            )
            if any(len(p) != 2 for p in pts):
                raise ZoneConfigError("Each line needs exactly two numbers: x%, y%.")
        name = zone_name.strip() or "Danger zone"
        draft = DangerZone(
            zone_id=safe_name(name.lower()),
            name=name,
            polygon=tuple((x / 100, y / 100) for x, y in pts),
            source_name=video_name,
        )
    except (ValueError, ZoneConfigError) as exc:
        error = str(exc)

    if submitted:
        if error:
            st.error(error)
        elif draft is not None:
            storage.save_zone(draft)
            st.toast(f"Saved zone {draft.name}", icon=":material/check_circle:")
            zones = storage.list_zones(video_name)

    if zones:
        st.markdown("**Saved zones**")
        for zone in zones:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"- {zone.name}" + ("" if zone.source_name else " *(all videos)*"))
            if c2.button("Delete", key=f"del_{zone.zone_id}_{zone.source_name}"):
                storage.delete_zone(zone.zone_id, zone.source_name)
                st.rerun()

with preview_col:
    preview = rgb_to_bgr(frame_rgb)  # drawing helpers use OpenCV's BGR colours
    show_draft = draft is not None and not error
    saved = [z for z in zones if not (show_draft and z.zone_id == draft.zone_id)]
    if saved:
        preview = draw_zones(preview, saved)
    if show_draft:
        preview = draw_zones(preview, [draft], active_zone_ids={draft.zone_id})
    st.image(bgr_to_rgb(preview), caption="First frame. Saved zones in amber, the zone being edited in red.", width="stretch")

# --- 3. Process ---------------------------------------------------------------

st.subheader("3. Detect potential hazards")
runs = storage.list_runs(video_name)
if runs:
    last = runs[0]
    st.markdown(f"Latest run #{last.id}: {STATUS_BADGES.get(last.status, last.status)}")
    if last.status == STATUS_FAILED and last.error_message:
        st.error(last.error_message, icon=":material/error:")

if not zones:
    st.warning("Save at least one danger zone before processing.")

label = "Retry processing" if runs and runs[0].status == STATUS_FAILED else "Process video"
if st.button(label, type="primary", disabled=not zones, icon=":material/play_arrow:"):
    summary = run_processing(video_path, config)
    if summary.status == STATUS_COMPLETED:
        st.success(
            f"Finished: {summary.frames_processed} frames at {summary.processing_fps:.1f} fps. "
            f"**{len(summary.event_ids)} potential-hazard event(s)** logged for human review."
        )
        st.page_link("views/events.py", label="Review the events", icon=":material/warning:")
        st.markdown(f"**Annotated video (run #{summary.run_id})**")
        show_video(summary.output_path)
    else:
        st.error(summary.error_message, icon=":material/error:")
        st.caption("Fix the problem above, then press **Retry processing**.")
else:
    completed = [r for r in runs if r.status == STATUS_COMPLETED and r.output_path]
    if completed:
        with st.expander(f"Annotated video from run #{completed[0].id}", expanded=True):
            show_video(completed[0].output_path)
