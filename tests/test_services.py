"""Tests for the service layer.

``Restic`` and ``get_connector`` are replaced inside ``django_recovery.services``
and the restore client's ``subprocess.run`` is faked, so no restic binary,
database, or connector is needed. Every call gets an explicit config with
``binary`` set, so binary resolution is a no-op.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from django_recovery import services
from tests.factories import make_config, make_snapshot


def _config(**overrides):
    return make_config(binary="/usr/bin/restic", tags=["test"], **overrides)


@dataclass
class FakeConnector:
    dump: list = field(default_factory=lambda: ["pg_dump", "-d", "appdb"])
    restore: list = field(default_factory=lambda: ["psql", "-d", "appdb"])
    env: dict = field(default_factory=lambda: {"PGPASSWORD": "secret"})
    stdin_filename: str = "default.sql"

    def dump_command(self):
        return list(self.dump)

    def restore_command(self):
        return list(self.restore)

    def extra_env(self):
        return dict(self.env)


@pytest.fixture
def restic(monkeypatch):
    """The mocked ``Restic`` instance services build (restic 0.19.1)."""
    instance = MagicMock(name="restic")
    instance.version_info.return_value = (0, 19, 1)
    monkeypatch.setattr(services, "Restic", MagicMock(return_value=instance))
    return instance


@pytest.fixture
def connector(monkeypatch):
    conn = FakeConnector()
    monkeypatch.setattr(services, "get_connector", MagicMock(return_value=conn))
    return conn


@pytest.fixture
def restore(restic, connector, monkeypatch):
    """A working dump -> restore pipe. Returns the restore-client mock.

    Tests set ``restic.snapshots.return_value`` and may flip the return codes
    on ``restic.dump_popen.return_value`` / ``restore.return_value``.
    """
    restic.dump_popen.return_value = SimpleNamespace(
        stdout=MagicMock(), returncode=0, wait=MagicMock(return_value=0)
    )
    client = MagicMock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(services.subprocess, "run", client)
    return client


# --- backup ---------------------------------------------------------------------

@pytest.mark.usefixtures("connector")
def test_backup_streams_each_database_through_restic(restic):
    logs = []
    summary = services.run_backup(config=_config(), log_callback=logs.append)

    restic.backup_command.assert_called_once_with(
        ["pg_dump", "-d", "appdb"],
        stdin_filename="default.sql",
        tags=["db:default", "test"],
        extra_env={"PGPASSWORD": "secret"},
        host=None,
        skip_if_unchanged=False,
        read_concurrency=None,
    )
    restic.backup_paths.assert_not_called()
    assert summary == {"default": "ok"}
    assert logs == ["Backing up database 'default'...", "Database 'default' backed up."]


@pytest.mark.usefixtures("connector")
def test_backup_forwards_host_and_tuning(restic):
    services.run_backup(config=_config(
        host="web1", skip_if_unchanged=True, tuning={"read_concurrency": 4},
    ))
    kwargs = restic.backup_command.call_args.kwargs
    assert (kwargs["host"], kwargs["skip_if_unchanged"], kwargs["read_concurrency"]) == (
        "web1", True, 4,
    )


@pytest.mark.usefixtures("connector")
def test_backup_includes_media_when_enabled(restic, settings):
    settings.MEDIA_ROOT = "/srv/media"
    summary = services.run_backup(config=_config(media=True, media_exclude=["*.tmp"]))

    restic.backup_paths.assert_called_once_with(
        ["/srv/media"],
        tags=["media", "test"],
        host=None,
        skip_if_unchanged=False,
        read_concurrency=None,
        exclude=["*.tmp"],
    )
    assert summary == {"default": "ok", "media": "ok"}


# --- restore --------------------------------------------------------------------------

def test_restore_by_id_pipes_dump_into_restore_client(restic, restore):
    restic.snapshots.return_value = [make_snapshot("abc123def456")]

    services.run_restore("default", "abc1", config=_config())  # id prefix, like restic

    restic.snapshots.assert_called_once_with(snapshot_ids=["abc1"])
    restic.dump_popen.assert_called_once_with("abc123def456", "default.sql")
    (argv,), kwargs = restore.call_args
    assert argv == ["psql", "-d", "appdb"]
    assert kwargs["stdin"] is restic.dump_popen.return_value.stdout
    assert kwargs["env"]["PGPASSWORD"] == "secret"
    restic.dump_popen.return_value.wait.assert_called_once()


@pytest.mark.parametrize("snapshots, expected", [
    pytest.param(
        [make_snapshot("old", time="2026-07-14T10:00:00Z"),
         make_snapshot("new", time="2026-07-14T12:00:00Z"),
         make_snapshot("other", time="2026-07-14T13:00:00Z", tags=("db:other",))],
        "new",
        id="newest-for-this-database",
    ),
    pytest.param(
        # 10:30+02:00 is 08:30Z: older, even though it sorts later as text.
        [make_snapshot("older", time="2026-07-14T10:30:00+02:00"),
         make_snapshot("newer", time="2026-07-14T09:00:00Z")],
        "newer",
        id="compares-across-timezone-offsets",
    ),
])
@pytest.mark.usefixtures("restore")
def test_restore_latest_picks_newest_snapshot(restic, snapshots, expected):
    restic.snapshots.return_value = snapshots

    services.run_restore("default", "latest", config=_config())

    restic.snapshots.assert_called_once_with(tags=["db:default"])
    restic.dump_popen.assert_called_once_with(expected, "default.sql")


@pytest.mark.parametrize("snapshot_id, snapshots, match", [
    ("abc123", [make_snapshot("abc123def456", tags=("db:other",))],
     "not a backup of database 'default'"),
    ("abc123", [], "snapshot abc123 not found"),
    ("latest", [], "snapshot latest not found"),
])
def test_restore_refuses_missing_or_foreign_snapshot(
    restic, restore, snapshot_id, snapshots, match
):
    restic.snapshots.return_value = snapshots

    with pytest.raises(ValueError, match=match):
        services.run_restore("default", snapshot_id, config=_config())

    restic.dump_popen.assert_not_called()
    restore.assert_not_called()


@pytest.mark.parametrize("dump_rc, restore_rc, match", [
    (1, 0, "restic dump failed"),
    (0, 3, "restore of database 'default' failed .exit code 3."),
])
def test_restore_reports_failing_process(restic, restore, dump_rc, restore_rc, match):
    restic.snapshots.return_value = [make_snapshot()]
    restic.dump_popen.return_value.returncode = dump_rc
    restore.return_value.returncode = restore_rc

    with pytest.raises(RuntimeError, match=match):
        services.run_restore("default", "abc123", config=_config())


# --- prune / remove / list ---------------------------------------------------------------

@pytest.mark.parametrize("dry_run", [False, True])
def test_prune_applies_retention_policy(restic, dry_run):
    services.run_prune(config=_config(retention={"daily": 7}), dry_run=dry_run)
    restic.forget_policy.assert_called_once_with(
        {"daily": 7}, prune=not dry_run, dry_run=dry_run
    )


def test_prune_without_retention_raises(restic):
    with pytest.raises(ValueError, match="RETENTION"):
        services.run_prune(config=_config())
    restic.forget_policy.assert_not_called()


def test_remove_snapshot_forgets_and_prunes(restic):
    services.remove_snapshot("abc123", config=_config())
    restic.forget_snapshot.assert_called_once_with("abc123", prune=True)


def test_list_snapshots_returns_restic_snapshots(restic):
    restic.snapshots.return_value = [make_snapshot()]
    assert services.list_snapshots(config=_config()) is restic.snapshots.return_value


# --- init -----------------------------------------------------------------------------------

@pytest.mark.parametrize("version, initialized, calls_init, log", [
    ((0, 19, 1), False, True, "Repository initialized."),
    ((0, 19, 1), True, False, "Repository already initialized; skipping."),
    (None, False, True, "Repository initialized."),  # unparsable version is let through
])
def test_init(restic, version, initialized, calls_init, log):
    restic.version_info.return_value = version
    restic.is_initialized.return_value = initialized
    logs = []

    services.run_init(config=_config(), log_callback=logs.append)

    assert restic.init.called is calls_init
    assert logs[-1] == log


def test_init_rejects_too_old_restic(restic):
    restic.version_info.return_value = (0, 15, 2)
    with pytest.raises(RuntimeError, match="restic 0.15.2 is too old.*0.16.0"):
        services.run_init(config=_config())
    restic.init.assert_not_called()


def test_make_restic_passes_tuning_timeout(monkeypatch):
    restic_cls = MagicMock()
    monkeypatch.setattr(services, "Restic", restic_cls)
    services._make_restic(_config(tuning={"timeout": 3600}))
    assert restic_cls.call_args.kwargs["timeout"] == 3600
