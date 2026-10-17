"""SQLite persistence for safety events, danger zones and processing runs (PRD §11).

Each operation opens its own short-lived connection, so a ``Storage`` object is
safe to share across Streamlit reruns and threads. All SQL uses parameters.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from constructsafe.events import HazardEvent
from constructsafe.zones import DangerZone

SCHEMA_VERSION = 1

REVIEW_NEW = "new"
REVIEW_REVIEWED = "reviewed"
REVIEW_STATUSES = (REVIEW_NEW, REVIEW_REVIEWED)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
RUN_STATUSES = (STATUS_PENDING, STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED)

_ANY_SOURCE = ""  # zones with no source_name apply to every source

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS processing_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name      TEXT NOT NULL,
    source_path      TEXT,
    status           TEXT NOT NULL CHECK (status IN {RUN_STATUSES}),
    error_message    TEXT,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    output_path      TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS safety_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER REFERENCES processing_runs(id),
    source_name        TEXT NOT NULL,
    timestamp_seconds  REAL NOT NULL,
    event_type         TEXT NOT NULL,
    zone_id            TEXT,
    evidence_path      TEXT,
    review_status      TEXT NOT NULL DEFAULT '{REVIEW_NEW}' CHECK (review_status IN {REVIEW_STATUSES}),
    description        TEXT NOT NULL,
    frame_index        INTEGER,
    first_seen_seconds REAL,
    workers_in_zone    INTEGER,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_source ON safety_events(source_name, timestamp_seconds);
CREATE INDEX IF NOT EXISTS idx_events_run ON safety_events(run_id);

CREATE TABLE IF NOT EXISTS danger_zones (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id      TEXT NOT NULL,
    source_name  TEXT NOT NULL DEFAULT '',
    name         TEXT NOT NULL,
    polygon_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (source_name, zone_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SafetyEvent:
    id: int
    run_id: int | None
    source_name: str
    timestamp_seconds: float
    event_type: str
    zone_id: str | None
    evidence_path: str | None  # relative to the evidence directory; None if capture failed
    review_status: str
    description: str
    frame_index: int | None
    first_seen_seconds: float | None
    workers_in_zone: int | None
    created_at: str

    @property
    def is_new(self) -> bool:
        return self.review_status == REVIEW_NEW


@dataclass(frozen=True)
class ProcessingRun:
    id: int
    source_name: str
    source_path: str | None
    status: str
    error_message: str | None
    frames_processed: int
    output_path: str | None
    created_at: str
    updated_at: str


class Storage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.database_path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:  # commit on success, roll back on error
                yield conn

    def _migrate(self) -> None:
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema v{version} is newer than this app supports (v{SCHEMA_VERSION})"
                )
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # --- processing runs (FR-08) ---------------------------------------------

    def create_run(self, source_name: str, source_path: str | None = None) -> int:
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO processing_runs (source_name, source_path, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (source_name, source_path, STATUS_PENDING, now, now),
            )
            return int(cur.lastrowid)

    def update_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        error_message: str | None = None,
        frames_processed: int | None = None,
        output_path: str | None = None,
    ) -> None:
        if status is not None and status not in RUN_STATUSES:
            raise ValueError(f"Unknown run status {status!r}")
        sets, params = ["updated_at = ?"], [_now()]
        for column, value in (
            ("status", status),
            ("error_message", error_message),
            ("frames_processed", frames_processed),
            ("output_path", output_path),
        ):
            if value is not None:
                sets.append(f"{column} = ?")
                params.append(value)
        if status in (STATUS_PROCESSING, STATUS_COMPLETED) and error_message is None:
            sets.append("error_message = NULL")  # a retry clears the previous failure
        params.append(run_id)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE processing_runs SET {', '.join(sets)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise KeyError(f"No processing run with id {run_id}")

    def fail_interrupted_runs(self) -> int:
        """Mark runs left ``processing`` (e.g. the app was stopped mid-run) as failed.

        Call once at app start-up, when no run can legitimately be in progress.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE processing_runs SET status = ?, error_message = ?, updated_at = ? WHERE status = ?",
                (
                    STATUS_FAILED,
                    "Processing was interrupted (the app stopped before it finished). Retry to process again.",
                    _now(),
                    STATUS_PROCESSING,
                ),
            )
            return cur.rowcount

    def get_run(self, run_id: int) -> ProcessingRun | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM processing_runs WHERE id = ?", (run_id,)).fetchone()
        return ProcessingRun(**dict(row)) if row else None

    def list_runs(self, source_name: str | None = None) -> list[ProcessingRun]:
        sql, params = "SELECT * FROM processing_runs", []
        if source_name is not None:
            sql += " WHERE source_name = ?"
            params.append(source_name)
        sql += " ORDER BY id DESC"
        with self._connect() as conn:
            return [ProcessingRun(**dict(r)) for r in conn.execute(sql, params)]

    # --- safety events (FR-06) -------------------------------------------------

    def add_event(
        self,
        event: HazardEvent,
        *,
        source_name: str,
        run_id: int | None,
        evidence_path: str | None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO safety_events (run_id, source_name, timestamp_seconds, event_type, zone_id,"
                " evidence_path, review_status, description, frame_index, first_seen_seconds,"
                " workers_in_zone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    source_name,
                    event.timestamp_seconds,
                    event.event_type,
                    event.zone_id,
                    evidence_path,
                    REVIEW_NEW,
                    event.description,
                    event.frame_index,
                    event.first_seen_seconds,
                    event.workers_in_zone,
                    _now(),
                ),
            )
            return int(cur.lastrowid)

    def get_event(self, event_id: int) -> SafetyEvent | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM safety_events WHERE id = ?", (event_id,)).fetchone()
        return SafetyEvent(**dict(row)) if row else None

    def list_events(
        self,
        *,
        source_name: str | None = None,
        run_id: int | None = None,
        review_status: str | None = None,
    ) -> list[SafetyEvent]:
        clauses, params = [], []
        for column, value in (("source_name", source_name), ("run_id", run_id), ("review_status", review_status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM safety_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY source_name, run_id, timestamp_seconds, id"
        with self._connect() as conn:
            return [SafetyEvent(**dict(r)) for r in conn.execute(sql, params)]

    def count_events(self) -> dict[str, int]:
        """Event counts by review status, plus ``total``."""
        counts = {status: 0 for status in REVIEW_STATUSES}
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT review_status, COUNT(*) AS n FROM safety_events GROUP BY review_status"
            ):
                counts[row["review_status"]] = row["n"]
        counts["total"] = sum(counts[s] for s in REVIEW_STATUSES)
        return counts

    def set_review_status(self, event_id: int, review_status: str) -> None:
        if review_status not in REVIEW_STATUSES:
            raise ValueError(f"Unknown review status {review_status!r}")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE safety_events SET review_status = ? WHERE id = ?", (review_status, event_id)
            )
            if cur.rowcount == 0:
                raise KeyError(f"No safety event with id {event_id}")

    # --- danger zones (FR-03) --------------------------------------------------

    def save_zone(self, zone: DangerZone) -> None:
        """Insert or replace a zone (keyed by ``source_name`` + ``zone_id``)."""
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO danger_zones (zone_id, source_name, name, polygon_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (source_name, zone_id) DO UPDATE SET"
                " name = excluded.name, polygon_json = excluded.polygon_json, updated_at = excluded.updated_at",
                (
                    zone.zone_id,
                    zone.source_name or _ANY_SOURCE,
                    zone.name,
                    json.dumps([list(p) for p in zone.polygon]),
                    now,
                    now,
                ),
            )

    def list_zones(self, source_name: str | None = None) -> list[DangerZone]:
        """All zones, or those for ``source_name`` plus zones that apply to any source."""
        sql, params = "SELECT * FROM danger_zones", []
        if source_name is not None:
            sql += " WHERE source_name IN (?, ?)"
            params += [source_name, _ANY_SOURCE]
        sql += " ORDER BY source_name, zone_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            DangerZone(
                zone_id=r["zone_id"],
                name=r["name"],
                polygon=tuple((float(x), float(y)) for x, y in json.loads(r["polygon_json"])),
                source_name=r["source_name"] or None,
            )
            for r in rows
        ]

    def delete_zone(self, zone_id: str, source_name: str | None = None) -> bool:
        """Delete a zone configuration. Events that reference it are kept."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM danger_zones WHERE zone_id = ? AND source_name = ?",
                (zone_id, source_name or _ANY_SOURCE),
            )
            return cur.rowcount > 0
