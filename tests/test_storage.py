import sqlite3

import pytest

from constructsafe.events import EVENT_ZONE_ENTRY, HazardEvent
from constructsafe.storage import (
    REVIEW_NEW,
    REVIEW_REVIEWED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Storage,
)
from constructsafe.zones import DangerZone

SQUARE = ((0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6))


def hazard(t=1.5, zone="excavator", frame=15):
    return HazardEvent(
        zone_id=zone,
        event_type=EVENT_ZONE_ENTRY,
        frame_index=frame,
        timestamp_seconds=t,
        first_seen_seconds=t - 0.2,
        workers_in_zone=1,
        workers_entered=1,
    )


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "db" / "test.db")


def test_event_round_trip_has_prd_fields(storage):
    run_id = storage.create_run("site.mp4", "/videos/site.mp4")
    event_id = storage.add_event(hazard(), source_name="site.mp4", run_id=run_id, evidence_path="a.jpg")

    event = storage.get_event(event_id)

    assert event.source_name == "site.mp4"
    assert event.timestamp_seconds == 1.5
    assert event.event_type == EVENT_ZONE_ENTRY
    assert event.zone_id == "excavator"
    assert event.evidence_path == "a.jpg"
    assert event.review_status == REVIEW_NEW and event.is_new
    assert event.description == "Potential hazard requiring human review"
    assert event.first_seen_seconds == pytest.approx(1.3)
    assert event.created_at  # ISO timestamp
    assert storage.get_event(9999) is None


def test_events_persist_across_restarts(tmp_path):
    path = tmp_path / "persist.db"
    first = Storage(path)
    first.add_event(hazard(), source_name="site.mp4", run_id=first.create_run("site.mp4"), evidence_path=None)
    first.save_zone(DangerZone("excavator", "Excavator", SQUARE, source_name="site.mp4"))

    reopened = Storage(path)  # a fresh instance simulates an app restart

    assert len(reopened.list_events()) == 1
    assert reopened.list_zones("site.mp4")[0].polygon == SQUARE


def test_review_status_and_counts(storage):
    ids = [storage.add_event(hazard(t=i), source_name="site.mp4", run_id=None, evidence_path=None) for i in range(3)]
    storage.set_review_status(ids[1], REVIEW_REVIEWED)

    assert storage.count_events() == {REVIEW_NEW: 2, REVIEW_REVIEWED: 1, "total": 3}
    assert [e.id for e in storage.list_events(review_status=REVIEW_NEW)] == [ids[0], ids[2]]

    with pytest.raises(ValueError):
        storage.set_review_status(ids[0], "dismissed")
    with pytest.raises(KeyError):
        storage.set_review_status(9999, REVIEW_REVIEWED)


def test_list_events_filters_and_orders(storage):
    run_a = storage.create_run("a.mp4")
    run_b = storage.create_run("b.mp4")
    storage.add_event(hazard(t=5), source_name="a.mp4", run_id=run_a, evidence_path=None)
    storage.add_event(hazard(t=2), source_name="a.mp4", run_id=run_a, evidence_path=None)
    storage.add_event(hazard(t=1), source_name="b.mp4", run_id=run_b, evidence_path=None)

    assert [e.timestamp_seconds for e in storage.list_events(source_name="a.mp4")] == [2, 5]
    assert [e.source_name for e in storage.list_events(run_id=run_b)] == ["b.mp4"]


def test_count_on_empty_database(storage):
    assert storage.count_events() == {REVIEW_NEW: 0, REVIEW_REVIEWED: 0, "total": 0}


def test_run_status_lifecycle(storage):
    run_id = storage.create_run("site.mp4")
    assert storage.get_run(run_id).status == STATUS_PENDING

    storage.update_run(run_id, status=STATUS_PROCESSING)
    storage.update_run(run_id, status=STATUS_FAILED, error_message="Could not read frames", frames_processed=10)
    run = storage.get_run(run_id)
    assert (run.status, run.error_message, run.frames_processed) == (STATUS_FAILED, "Could not read frames", 10)

    storage.update_run(run_id, status=STATUS_COMPLETED, output_path="out.mp4")
    run = storage.get_run(run_id)
    assert run.status == STATUS_COMPLETED and run.error_message is None and run.output_path == "out.mp4"

    with pytest.raises(ValueError):
        storage.update_run(run_id, status="exploded")
    with pytest.raises(KeyError):
        storage.update_run(9999, status=STATUS_COMPLETED)


def test_list_runs_newest_first(storage):
    first = storage.create_run("a.mp4")
    second = storage.create_run("a.mp4")
    storage.create_run("b.mp4")
    assert [r.id for r in storage.list_runs("a.mp4")] == [second, first]


def test_zone_upsert_scoping_and_delete(storage):
    storage.save_zone(DangerZone("excavator", "Excavator", SQUARE, source_name="site.mp4"))
    storage.save_zone(DangerZone("excavator", "Excavator v2", SQUARE, source_name="site.mp4"))  # update
    storage.save_zone(DangerZone("excavator", "Other site", SQUARE, source_name="other.mp4"))
    storage.save_zone(DangerZone("gate", "Gate", SQUARE))  # applies to any source

    site = storage.list_zones("site.mp4")
    assert [(z.zone_id, z.name, z.source_name) for z in site] == [
        ("gate", "Gate", None),
        ("excavator", "Excavator v2", "site.mp4"),
    ]
    assert len(storage.list_zones()) == 3

    assert storage.delete_zone("excavator", "site.mp4")
    assert not storage.delete_zone("excavator", "site.mp4")
    assert [z.zone_id for z in storage.list_zones("site.mp4")] == ["gate"]


def test_sql_injection_in_source_name_is_stored_literally(storage):
    nasty = "x'); DROP TABLE safety_events; --"
    storage.add_event(hazard(), source_name=nasty, run_id=None, evidence_path=None)
    assert storage.list_events(source_name=nasty)[0].source_name == nasty


def test_database_rejects_invalid_review_status_directly(storage):
    with sqlite3.connect(storage.database_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO safety_events (source_name, timestamp_seconds, event_type, review_status,"
            " description, created_at) VALUES ('a', 0, 't', 'bogus', 'd', 'now')"
        )


def test_refuses_newer_schema(tmp_path):
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        Storage(path)
