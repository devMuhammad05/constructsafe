"""Safety event history and review (FR-07)."""

from __future__ import annotations

import streamlit as st

from constructsafe.evidence import EvidencePathError, resolve_evidence_path
from constructsafe.storage import REVIEW_NEW, REVIEW_REVIEWED, STATUS_COMPLETED
from ui_common import SAFETY_NOTICE, event_type_label, format_time, format_utc, get_config, get_storage

config = get_config()
storage = get_storage()

st.header("Safety events")
st.warning(SAFETY_NOTICE, icon=":material/warning:")

counts = storage.count_events()
c1, c2, c3 = st.columns(3)
c1.metric("Potential-hazard events", counts["total"])
c2.metric("New (not yet reviewed)", counts[REVIEW_NEW])
c3.metric("Reviewed", counts[REVIEW_REVIEWED])

if counts["total"] == 0:
    st.info("No events yet. Process a video to detect potential hazards.")
    st.page_link("views/process.py", label="Process a video", icon=":material/upload:")
    st.stop()

all_events = storage.list_events()
sources = sorted({e.source_name for e in all_events})
f1, f2, f3 = st.columns([2, 1, 1])
source_filter = f1.selectbox("Video", ["All videos", *sources])
status_filter = f2.selectbox("Review status", ["All", "New", "Reviewed"])
latest_only = f3.toggle("Latest run per video only", value=True, help="Hide events from earlier runs of the same video.")

events = all_events
if source_filter != "All videos":
    events = [e for e in events if e.source_name == source_filter]
if status_filter != "All":
    wanted = REVIEW_NEW if status_filter == "New" else REVIEW_REVIEWED
    events = [e for e in events if e.review_status == wanted]
if latest_only:
    latest_run = {}
    for run in storage.list_runs():
        latest_completed = latest_run.get(run.source_name)
        if latest_completed is None and run.status == STATUS_COMPLETED:
            latest_run[run.source_name] = run.id
    events = [e for e in events if e.run_id is None or latest_run.get(e.source_name) in (None, e.run_id)]

if not events:
    st.info("No events match these filters.")
    st.stop()

rows = [
    {
        "ID": e.id,
        "Status": "🆕 New" if e.is_new else "✅ Reviewed",
        "Video": e.source_name,
        "Time in video": format_time(e.timestamp_seconds),
        "Event": event_type_label(e.event_type),
        "Zone": e.zone_id or "-",
        "Workers in zone": e.workers_in_zone,
        "Run": e.run_id,
        "Logged at": format_utc(e.created_at),
    }
    for e in events
]
st.caption("Select a row to see the evidence and mark it reviewed.")
table = st.dataframe(
    rows,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="events_table",
)

selected = [i for i in table.selection.rows if i < len(events)]  # filters may have shrunk the list
event = events[selected[0]] if selected else events[0]

st.divider()
detail, image_col = st.columns([2, 3])
with detail:
    st.subheader(f"Event #{event.id}")
    st.markdown(f"**{event_type_label(event.event_type)}**")
    st.markdown(
        f"""
- **Video:** {event.source_name}
- **Time in video:** {format_time(event.timestamp_seconds)} (first seen {format_time(event.first_seen_seconds)})
- **Zone:** {event.zone_id or '-'}
- **Workers in zone:** {event.workers_in_zone if event.workers_in_zone is not None else '-'}
- **Review status:** {'New' if event.is_new else 'Reviewed'}
"""
    )
    st.caption(event.description)
    if event.is_new:
        if st.button("Mark as reviewed", type="primary", icon=":material/check:"):
            storage.set_review_status(event.id, REVIEW_REVIEWED)
            st.rerun()
    elif st.button("Mark as new", icon=":material/undo:"):
        storage.set_review_status(event.id, REVIEW_NEW)
        st.rerun()

with image_col:
    if not event.evidence_path:
        st.info("No evidence screenshot was saved for this event.")
    else:
        try:
            path = resolve_evidence_path(config.evidence_dir, event.evidence_path)
        except EvidencePathError:
            st.error("This event's evidence path is invalid, so it isn't shown.")
        else:
            if path.is_file():
                st.image(str(path), caption=f"Evidence at {format_time(event.timestamp_seconds)}", width="stretch")
            else:
                st.info("The evidence screenshot file is missing from local storage.")
