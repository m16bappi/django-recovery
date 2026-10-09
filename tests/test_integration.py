"""End-to-end test with a real restic binary and a real SQLite database.

Runs init, backup, list, restore, and remove against a throwaway repository.
It uses a standalone SQLite file (not the test runner's database, which the
connector's separate dump process could not see), so no ORM access is needed.

Skipped when restic is not on ``PATH``; select it with ``pytest -m integration``.
"""

import shutil

import pytest

from django_recovery import services
from django_recovery.storage import Repository
from tests.factories import create_notes_db, make_config, read_notes

RESTIC = shutil.which("restic")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(RESTIC is None, reason="restic binary not available"),
]


def test_sqlite_backup_restore_roundtrip(tmp_path, settings):
    db = create_notes_db(tmp_path / "app.sqlite3", "hello-restic")
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db)}}
    config = make_config(
        repository=Repository(url=str(tmp_path / "repo")),
        password="test-pass",
        tags=["itest"],
        binary=RESTIC,
    )

    services.run_init(config)
    services.run_backup(config=config)
    (snapshot,) = services.list_snapshots(config=config)
    assert {"db:default", "itest"} <= set(snapshot.tags)

    # Change the data so the restore has a visible effect.
    db.unlink()
    create_notes_db(db, "changed")

    services.run_restore("default", "latest", config=config)
    assert read_notes(db) == ["hello-restic"]

    services.remove_snapshot(snapshot.id, config=config)
    assert services.list_snapshots(config=config) == []
