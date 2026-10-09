"""Plain builders shared across test modules.

Fixtures live in ``conftest.py``; these are ordinary functions so tests can
call them with arguments (and use them inside ``parametrize`` tables).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from django_recovery.conf import RecoveryConfig
from django_recovery.restic import Snapshot
from django_recovery.storage import Repository


def make_config(**overrides) -> RecoveryConfig:
    """A valid :class:`RecoveryConfig` for a local ``/repo`` repository."""
    fields = {"repository": Repository(url="/repo"), "databases": ["default"]}
    return RecoveryConfig(**{**fields, **overrides})


def recovery_settings(**overrides) -> dict:
    """A minimal valid ``settings.RECOVERY`` dict, with ``overrides`` applied.

    Pass ``KEY=None`` to leave a key effectively unset.
    """
    return {"STORAGE": "recovery", "PASSWORD": "test-password", **overrides}


def make_snapshot(
    snapshot_id: str = "abc123def456",
    *,
    tags: tuple[str, ...] = ("db:default",),
    time: str = "2026-07-14T10:00:00Z",
) -> Snapshot:
    return Snapshot(id=snapshot_id, short_id=snapshot_id[:8], time=time, tags=list(tags))


def create_notes_db(path: Path, *bodies: str) -> Path:
    """Create a SQLite file with a ``note`` table holding ``bodies``."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS note(id INTEGER PRIMARY KEY, body TEXT)")
        conn.executemany("INSERT INTO note(body) VALUES (?)", [(b,) for b in bodies])
        conn.commit()
    finally:
        conn.close()
    return path


def read_notes(path: Path) -> list[str]:
    conn = sqlite3.connect(str(path))
    try:
        return [row[0] for row in conn.execute("SELECT body FROM note ORDER BY id")]
    finally:
        conn.close()
