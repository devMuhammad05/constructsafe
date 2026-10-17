"""Evidence screenshots for potential-hazard events (FR-06).

Images are written only under the configured evidence directory. The database
stores paths *relative* to that directory, and every read resolves them back
through :func:`resolve_evidence_path`, which refuses anything that would
escape it (path traversal).
"""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from constructsafe.events import HazardEvent

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
JPEG_QUALITY = 90


class EvidencePathError(ValueError):
    """Raised when an evidence path would resolve outside the evidence directory."""


def safe_name(text: str, max_length: int = 60) -> str:
    """Reduce arbitrary text (an uploaded file name, a zone id) to a safe file-name fragment."""
    cleaned = _UNSAFE_CHARS.sub("_", text).strip("._")
    return (cleaned or "unnamed")[:max_length]


def evidence_filename(run_id: int, source_name: str, event: HazardEvent) -> str:
    return (
        f"run{run_id:05d}_{safe_name(Path(source_name).stem)}_"
        f"f{event.frame_index:07d}_{safe_name(event.zone_id)}_{safe_name(event.event_type)}.jpg"
    )


def resolve_evidence_path(evidence_dir: Path, relative_path: str) -> Path:
    """Turn a stored relative path back into an absolute one, inside ``evidence_dir`` only."""
    root = evidence_dir.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise EvidencePathError(f"Evidence path escapes the evidence directory: {relative_path!r}")
    return candidate


def save_evidence(
    evidence_dir: Path,
    image: np.ndarray,
    *,
    run_id: int,
    source_name: str,
    event: HazardEvent,
) -> str:
    """Write the evidence JPEG and return its path relative to ``evidence_dir``.

    Raises ``OSError`` if the image can't be written.
    """
    relative = evidence_filename(run_id, source_name, event)
    target = resolve_evidence_path(evidence_dir, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(target), image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise OSError(f"Could not write evidence image {target.name}")
    return relative
