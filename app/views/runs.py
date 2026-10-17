"""Processing run history with status, errors and retry (FR-08)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from constructsafe.sources import VideoValidationError
from constructsafe.storage import STATUS_COMPLETED, STATUS_FAILED
from constructsafe.uploads import resolve_video
from ui_common import STATUS_BADGES, format_utc, get_config, get_storage, run_processing

config = get_config()
storage = get_storage()

st.header("Processing runs")
runs = storage.list_runs()
if not runs:
    st.info("No videos have been processed yet.")
    st.page_link("views/process.py", label="Process a video", icon=":material/upload:")
    st.stop()

event_counts: dict[int, int] = {}
for event in storage.list_events():
    if event.run_id is not None:
        event_counts[event.run_id] = event_counts.get(event.run_id, 0) + 1

latest_run_id: dict[str, int] = {}
for run in runs:  # newest first
    latest_run_id.setdefault(run.source_name, run.id)

for run in runs:
    with st.container(border=True):
        top = st.columns([3, 2, 2, 2])
        top[0].markdown(f"**Run #{run.id}: {run.source_name}**")
        top[1].markdown(STATUS_BADGES.get(run.status, run.status))
        top[2].markdown(f"{run.frames_processed} frames")
        top[3].markdown(f"{event_counts.get(run.id, 0)} event(s)")
        st.caption(f"Started {format_utc(run.created_at)} · updated {format_utc(run.updated_at)}")
        if run.status == STATUS_FAILED:
            st.error(run.error_message or "Processing failed.", icon=":material/error:")
            if latest_run_id[run.source_name] != run.id:
                st.caption(f"Superseded by run #{latest_run_id[run.source_name]}.")
                continue
            try:
                video = resolve_video(config, Path(run.source_name).name)
            except VideoValidationError:
                video = None
            if video is not None and video.is_file():
                if st.button("Retry", key=f"retry_{run.id}", icon=":material/refresh:"):
                    summary = run_processing(video, config)
                    if summary.status == STATUS_COMPLETED:
                        st.success(f"Retry run #{summary.run_id} completed with {len(summary.event_ids)} event(s).")
                    else:
                        st.error(summary.error_message)
            else:
                st.caption("The video is no longer in local storage. Upload it again to retry.")
