"""Central configuration.

Every tunable value lives here so pipeline code never hardcodes it. Values can
be overridden with environment variables prefixed ``CONSTRUCTSAFE_`` (for
example ``CONSTRUCTSAFE_CONFIDENCE_THRESHOLD=0.5``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALERT_LABEL = "Potential hazard - requires human review"


@dataclass(frozen=True)
class Config:
    # Detection
    model_weights: str = "yolo11n.pt"
    confidence_threshold: float = 0.35
    inference_image_size: int = 640
    device: str = "cpu"

    # Video processing
    frame_stride: int = 1  # process every Nth frame; raise on slow machines
    max_frame_width: int = 1280  # downscale wider frames before inference; 0 = never

    # Event logic (Phase 2): frames a worker must stay in/out before the state flips
    enter_persistence_frames: int = 3
    exit_persistence_frames: int = 5

    # Upload validation
    allowed_video_extensions: tuple[str, ...] = (".mp4", ".avi", ".mov", ".mkv")

    # Storage
    data_dir: Path = field(default=PROJECT_ROOT / "data")
    models_dir: Path = field(default=PROJECT_ROOT / "models")

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "constructsafe.db"

    @property
    def model_path(self) -> Path:
        """Weights are kept in ``models/`` (git-ignored); Ultralytics downloads them there."""
        weights = Path(self.model_weights)
        return weights if weights.is_absolute() else self.models_dir / weights


def _coerce(raw: str, current: object) -> object:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, Path):
        return Path(raw)
    if isinstance(current, tuple):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return raw


def load_config(**overrides: object) -> Config:
    """Build a Config from defaults, then ``CONSTRUCTSAFE_*`` env vars, then ``overrides``."""
    defaults = Config()
    values: dict[str, object] = {}
    for f in fields(Config):
        raw = os.environ.get(f"CONSTRUCTSAFE_{f.name.upper()}")
        if raw is not None:
            values[f.name] = _coerce(raw, getattr(defaults, f.name))
    values.update(overrides)
    return Config(**values)
