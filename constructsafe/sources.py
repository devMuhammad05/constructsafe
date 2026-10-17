"""Frame sources.

The pipeline consumes any iterable of :class:`Frame`. ConstructSafe processes
uploaded, recorded video files only (live camera input is out of scope).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


class VideoValidationError(ValueError):
    """Raised when a video file is missing, has an unsupported type or can't be decoded."""


@dataclass(frozen=True)
class Frame:
    index: int  # frame number in the original source
    timestamp_seconds: float  # position in the video
    image: np.ndarray  # BGR, as OpenCV reads it


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    width: int
    height: int

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.fps if self.fps > 0 else 0.0


class FrameSource(Protocol):
    name: str

    def __iter__(self) -> Iterator[Frame]: ...


def validate_video_file(path: str | Path, allowed_extensions: tuple[str, ...]) -> VideoInfo:
    """Check the file type and that OpenCV can decode at least one frame (FR-01)."""
    path = Path(path)
    if not path.is_file():
        raise VideoValidationError(f"Video file not found: {path.name}")
    if path.suffix.lower() not in {ext.lower() for ext in allowed_extensions}:
        allowed = ", ".join(allowed_extensions)
        raise VideoValidationError(
            f"Unsupported file type '{path.suffix or '(none)'}'. Supported types: {allowed}."
        )

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoValidationError(f"Could not open '{path.name}'. The file may be corrupt.")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise VideoValidationError(f"Could not read any frames from '{path.name}'.")
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        height, width = frame.shape[:2]
    finally:
        capture.release()

    return VideoInfo(path=path, fps=fps, frame_count=frame_count, width=width, height=height)


def resize_to_max_width(image: np.ndarray, max_width: int) -> np.ndarray:
    """Downscale (never upscale) so the width is at most ``max_width``. 0 disables it."""
    height, width = image.shape[:2]
    if max_width <= 0 or width <= max_width:
        return image
    scale = max_width / width
    return cv2.resize(image, (max_width, round(height * scale)), interpolation=cv2.INTER_AREA)


def read_frame(path: str | Path, frame_index: int) -> Frame:
    """Read a single frame by index (used by evaluation tools)."""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoValidationError(f"Could not open '{Path(path).name}'.")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, image = capture.read()
        if not ok or image is None:
            raise VideoValidationError(f"Could not read frame {frame_index} of '{Path(path).name}'.")
        return Frame(index=frame_index, timestamp_seconds=frame_index / fps, image=image)
    finally:
        capture.release()


class VideoFileSource:
    """Yields every ``frame_stride``-th frame of a video file."""

    def __init__(
        self,
        path: str | Path,
        *,
        frame_stride: int = 1,
        max_width: int = 0,
        allowed_extensions: tuple[str, ...] = (".mp4", ".avi", ".mov", ".mkv"),
    ) -> None:
        if frame_stride < 1:
            raise ValueError("frame_stride must be at least 1")
        self.info = validate_video_file(path, allowed_extensions)
        self.name = self.info.path.name
        self.frame_stride = frame_stride
        self.max_width = max_width

    def __iter__(self) -> Iterator[Frame]:
        capture = cv2.VideoCapture(str(self.info.path))
        if not capture.isOpened():
            raise VideoValidationError(f"Could not open '{self.name}'.")
        fps = self.info.fps if self.info.fps > 0 else 30.0  # some containers report 0
        index = 0
        try:
            while True:
                # grab() skips decoding for frames the stride drops
                if index % self.frame_stride == 0:
                    ok, image = capture.read()
                    if not ok:
                        break
                    yield Frame(
                        index=index,
                        timestamp_seconds=index / fps,
                        image=resize_to_max_width(image, self.max_width),
                    )
                elif not capture.grab():
                    break
                index += 1
        finally:
            capture.release()
