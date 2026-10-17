"""Shared Streamlit helpers: cached resources, formatting and the processing runner."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from constructsafe.config import Config, load_config
from constructsafe.detection import YoloDetector
from constructsafe.pipeline import EVENT_TYPE_LABELS, FrameResult, ProcessingSummary, process_video
from constructsafe.sources import VideoFileSource
from constructsafe.storage import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Storage,
)
from constructsafe.video_out import video_mime_type

SAFETY_NOTICE = (
    "Alerts are **potential hazards requiring human review**. ConstructSafe is a review aid. "
    "It is not a substitute for trained safety personnel or site safety procedures, and it "
    "does not guarantee safety."
)

STATUS_BADGES = {
    STATUS_PENDING: ":gray-badge[Pending]",
    STATUS_PROCESSING: ":blue-badge[Processing]",
    STATUS_COMPLETED: ":green-badge[Completed]",
    STATUS_FAILED: ":red-badge[Failed]",
}


@st.cache_resource
def get_base_config() -> Config:
    return load_config()


def get_config() -> Config:
    """Base config plus the settings chosen in the sidebar for this session."""
    base = get_base_config()
    overrides = st.session_state.get("config_overrides", {})
    return replace(base, **overrides) if overrides else base


@st.cache_resource
def get_storage() -> Storage:
    storage = Storage(get_base_config().database_path)
    # runs once per server process: anything still "processing" was interrupted
    storage.fail_interrupted_runs()
    return storage


@st.cache_resource(show_spinner="Loading the detection model…")
def get_detector(weights: str, image_size: int, device: str) -> YoloDetector:
    detector = YoloDetector(weights, confidence_threshold=0.35, image_size=image_size, device=device)
    detector.warmup()
    return detector


def detector_for(config: Config) -> YoloDetector:
    detector = get_detector(str(config.model_path), config.inference_image_size, config.device)
    detector.confidence_threshold = config.confidence_threshold
    return detector


def format_time(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def format_utc(iso_timestamp: str) -> str:
    """'2026-10-17T21:24:22+00:00' -> '2026-10-17 21:24:22 UTC'."""
    return iso_timestamp.replace("T", " ").removesuffix("+00:00") + " UTC"


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type, event_type)


@st.cache_data(show_spinner=False, max_entries=16)
def first_frame(path: str, mtime: float, max_width: int) -> np.ndarray:
    """First frame as RGB (cached per file version)."""
    frame = next(iter(VideoFileSource(path, max_width=max_width, allowed_extensions=(Path(path).suffix,))))
    return cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)


def bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def rgb_to_bgr(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def show_video(path: str | Path) -> None:
    path = Path(path)
    if path.is_file():
        st.video(path.read_bytes(), format=video_mime_type(path))
    else:
        st.info("The annotated video file is no longer available.")


def run_processing(video_path: Path, config: Config) -> ProcessingSummary:
    """Process a video with live progress, a preview and the run status (FR-08)."""
    storage = get_storage()
    run_id = storage.create_run(video_path.name, str(video_path))

    status = st.status(f"Processing {video_path.name}…", expanded=True)
    with status:
        badge = st.empty()
        badge.markdown(f"Run #{run_id} {STATUS_BADGES[STATUS_PENDING]}")
        progress = st.progress(0.0, text="Loading the detection model…")
        preview = st.empty()
        counter = st.empty()
        detector = detector_for(config)
        events_so_far = 0

        def on_progress(done: int, expected: int) -> None:
            if done == 1:
                badge.markdown(f"Run #{run_id} {STATUS_BADGES[STATUS_PROCESSING]}")
            fraction = min(done / expected, 1.0) if expected else 0.0
            progress.progress(fraction, text=f"{done} / {expected or '?'} frames processed")

        def on_frame(result: FrameResult) -> None:
            nonlocal events_so_far
            events_so_far += len(result.events)
            # refresh the preview every few frames, and always on an event
            if result.events or result.frame.index % (config.frame_stride * 5) == 0:
                preview.image(bgr_to_rgb(result.annotated), caption=f"t = {format_time(result.frame.timestamp_seconds)}")
            counter.markdown(f"Potential-hazard events so far: **{events_so_far}**")

        summary = process_video(
            video_path, config, storage, detector=detector, on_progress=on_progress, on_frame=on_frame, run_id=run_id
        )

    if summary.status == STATUS_COMPLETED:
        status.update(label=f"Completed: {video_path.name} ({len(summary.event_ids)} event(s))", state="complete", expanded=False)
    else:
        status.update(label=f"Failed: {video_path.name}", state="error", expanded=True)
    return summary
