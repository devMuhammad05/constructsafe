"""Saving and validating uploaded videos (FR-01). No Streamlit dependency."""

from __future__ import annotations

from pathlib import Path

from constructsafe.config import Config
from constructsafe.evidence import safe_name
from constructsafe.sources import VideoInfo, VideoValidationError, validate_video_file


def upload_target(filename: str, config: Config) -> Path:
    """Where an upload called ``filename`` is stored: a sanitised name inside ``videos_dir``."""
    original = Path(filename)
    suffix = original.suffix.lower()
    if suffix not in {ext.lower() for ext in config.allowed_video_extensions}:
        allowed = ", ".join(config.allowed_video_extensions)
        raise VideoValidationError(f"Unsupported file type '{suffix or '(none)'}'. Supported types: {allowed}.")
    return config.videos_dir / f"{safe_name(original.stem)}{suffix}"


def save_upload(data: bytes, filename: str, config: Config) -> VideoInfo:
    """Write an uploaded video to local storage and check it can be decoded.

    The file type is checked before anything is written. A file that can't be
    decoded is deleted again and a :class:`VideoValidationError` explains why.
    Re-uploading the same name replaces the earlier file, so zones saved for
    that video keep applying.
    """
    target = upload_target(filename, config)
    if not data:
        raise VideoValidationError(f"'{filename}' is empty.")
    target.parent.mkdir(parents=True, exist_ok=True)
    # keep the real extension on the temporary file so the decoder can recognise the container
    partial = target.with_name(f"{target.stem}.uploading{target.suffix}")
    partial.write_bytes(data)
    try:
        validate_video_file(partial, (partial.suffix,))
    except VideoValidationError as exc:
        partial.unlink(missing_ok=True)
        raise VideoValidationError(
            f"'{filename}' could not be read as a video. The file may be corrupt or use an "
            "unsupported codec."
        ) from exc
    partial.replace(target)
    return validate_video_file(target, config.allowed_video_extensions)


def list_videos(config: Config) -> list[Path]:
    """Videos already in local storage, newest first."""
    if not config.videos_dir.is_dir():
        return []
    allowed = {ext.lower() for ext in config.allowed_video_extensions}
    files = [p for p in config.videos_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_video(config: Config, name: str) -> Path:
    """Map a stored video name back to its path, refusing anything outside ``videos_dir``."""
    root = config.videos_dir.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise VideoValidationError(f"Invalid video name: {name!r}")
    return candidate
