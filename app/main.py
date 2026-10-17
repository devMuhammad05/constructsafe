"""ConstructSafe Streamlit app.

Run with:  uv run streamlit run app/main.py
"""

from __future__ import annotations

import streamlit as st

from ui_common import SAFETY_NOTICE, get_base_config, get_storage

st.set_page_config(page_title="ConstructSafe", page_icon="⚠️", layout="wide")

pages = st.navigation(
    [
        st.Page("views/process.py", title="Process video", icon=":material/upload:", default=True),
        st.Page("views/events.py", title="Safety events", icon=":material/warning:"),
        st.Page("views/runs.py", title="Processing runs", icon=":material/history:"),
    ]
)

base = get_base_config()
get_storage()  # create the database and recover interrupted runs on start-up

with st.sidebar:
    st.title("ConstructSafe")
    st.caption(SAFETY_NOTICE)
    with st.expander("Detection settings"):
        conf = st.slider(
            "Confidence threshold",
            0.05,
            0.95,
            float(st.session_state.get("config_overrides", {}).get("confidence_threshold", base.confidence_threshold)),
            0.05,
            help="Person detections below this confidence are ignored.",
        )
        stride = st.number_input(
            "Process every Nth frame",
            1,
            30,
            int(st.session_state.get("config_overrides", {}).get("frame_stride", base.frame_stride)),
            help="Higher is faster on slow machines but may miss brief entries.",
        )
        st.session_state["config_overrides"] = {"confidence_threshold": conf, "frame_stride": int(stride)}
        st.caption(
            f"Entry needs {base.enter_persistence_frames} processed frames in the zone. "
            f"The warning clears after {base.exit_persistence_frames} frames out."
        )

pages.run()
