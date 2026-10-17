"""Writing annotated videos in a format browsers can play.

OpenCV's default ``mp4v`` codec doesn't play in browsers, so try H.264 MP4
first, then VP8 WebM, and fall back to ``mp4v`` only if neither is available
in this OpenCV build.
"""

from __future__ import annotations

from pathlib import Path

import cv2

# (fourcc, file extension), in order of preference
CODEC_PREFERENCE = (("avc1", ".mp4"), ("VP80", ".webm"), ("mp4v", ".mp4"))


def open_video_writer(path_without_suffix: Path, fps: float, size: tuple[int, int]) -> tuple[cv2.VideoWriter, Path]:
    """Open a writer for ``(width, height)`` frames and return it with the chosen path."""
    path_without_suffix.parent.mkdir(parents=True, exist_ok=True)
    for fourcc, suffix in CODEC_PREFERENCE:
        path = path_without_suffix.with_suffix(suffix)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, size)
        if writer.isOpened():
            return writer, path
        writer.release()
        path.unlink(missing_ok=True)
    raise OSError(f"No usable video codec to write {path_without_suffix.name}")


def video_mime_type(path: str | Path) -> str:
    return "video/webm" if Path(path).suffix.lower() == ".webm" else "video/mp4"
