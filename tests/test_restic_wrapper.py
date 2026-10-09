"""Tests for the restic CLI wrapper.

``subprocess.run`` / ``subprocess.Popen`` are faked; tests assert the exact
argv and environment the wrapper builds. No real restic binary is required.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from django_recovery import restic as restic_mod
from django_recovery.restic import Restic, ResticError, Snapshot

BASE = ["restic", "--json", "-r", "/repo"]
DUMP = ["pg_dump", "-d", "app"]


class FakeRun:
    """Stands in for ``subprocess.run``: records calls, returns a set result."""

    def __init__(self):
        self.calls = []
        self.stdout = ""
        self.stderr = ""
        self.returncode = 0

    def __call__(self, argv, **kwargs):
        self.calls.append(SimpleNamespace(argv=argv, kwargs=kwargs))
        return SimpleNamespace(
            returncode=self.returncode, stdout=self.stdout, stderr=self.stderr
        )

    @property
    def argv(self):
        return self.calls[-1].argv

    @property
    def kwargs(self):
        return self.calls[-1].kwargs


@pytest.fixture
def run(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(restic_mod.subprocess, "run", fake)
    return fake


@pytest.fixture
def restic():
    return Restic(repository="/repo", binary="restic")


@pytest.mark.parametrize("call, expected", [
    pytest.param(lambda r: r.init(), ["init"], id="init"),
    pytest.param(lambda r: r.unlock(), ["unlock"], id="unlock"),
    pytest.param(lambda r: r.is_initialized(), ["cat", "config"], id="is_initialized"),
    pytest.param(
        lambda r: r.backup_command(DUMP, stdin_filename="default.sql"),
        ["backup", "--stdin-filename", "default.sql",
         "--stdin-from-command", "--", *DUMP],
        id="backup_command-minimal",
    ),
    pytest.param(
        lambda r: r.backup_command(
            DUMP, stdin_filename="default.sql", tags=["db:default", "prod"],
            host="web1", skip_if_unchanged=True, read_concurrency=4,
        ),
        ["backup", "--stdin-filename", "default.sql",
         "--tag", "db:default", "--tag", "prod",
         "--host", "web1", "--skip-if-unchanged", "--read-concurrency", "4",
         "--stdin-from-command", "--", *DUMP],
        id="backup_command-all-flags",
    ),
    pytest.param(
        lambda r: r.backup_paths(["/media"], tags=["media"], exclude=["*.tmp", "cache/*"]),
        ["backup", "/media", "--tag", "media",
         "--exclude", "*.tmp", "--exclude", "cache/*"],
        id="backup_paths",
    ),
    pytest.param(
        lambda r: r.snapshots(tags=["db:default"], snapshot_ids=["abc1"]),
        ["snapshots", "--tag", "db:default", "abc1"],
        id="snapshots-filtered",
    ),
    pytest.param(
        lambda r: r.forget_snapshot("abc123"),
        ["forget", "abc123", "--prune"],
        id="forget_snapshot",
    ),
    pytest.param(
        lambda r: r.forget_snapshot("abc123", prune=False),
        ["forget", "abc123"],
        id="forget_snapshot-no-prune",
    ),
    pytest.param(
        lambda r: r.forget_policy({"daily": 7, "weekly": 4, "last": 5, "within": "7d"}),
        ["forget", "--group-by", "paths,tags", "--keep-last", "5", "--keep-daily", "7",
         "--keep-weekly", "4", "--keep-within", "7d", "--prune"],
        id="forget_policy",
    ),
    pytest.param(
        lambda r: r.forget_policy({"daily": 7}, prune=False, dry_run=True),
        ["forget", "--group-by", "paths,tags", "--keep-daily", "7", "--dry-run"],
        id="forget_policy-dry-run",
    ),
])
def test_argv(run, restic, call, expected):
    run.stdout = "[]"  # parsed by snapshots(), ignored elsewhere
    call(restic)
    assert run.argv == BASE + expected


def test_global_args_go_after_the_repository(run):
    Restic(repository="/repo", binary="restic",
           global_args=["--compression", "max"]).init()
    assert run.argv == BASE + ["--compression", "max", "init"]


def test_dump_popen_streams_raw_bytes_without_json(monkeypatch):
    popen = []
    monkeypatch.setattr(
        restic_mod.subprocess, "Popen",
        lambda argv, **kwargs: popen.append((argv, kwargs)) or SimpleNamespace(),
    )
    Restic(repository="/repo", binary="restic").dump_popen("latest", "default.sql")
    argv, kwargs = popen[0]
    assert argv == ["restic", "-r", "/repo", "dump", "latest", "default.sql"]
    assert kwargs["stdout"] is subprocess.PIPE
    assert "env" in kwargs


@pytest.mark.parametrize("returncode, expected", [(0, True), (1, False)])
def test_is_initialized(run, restic, returncode, expected):
    run.returncode = returncode
    assert restic.is_initialized() is expected


def test_snapshots_parses_json_and_tolerates_missing_fields(run, restic):
    run.stdout = json.dumps([
        {"id": "aaaa1111bbbb2222", "short_id": "aaaa1111", "time": "2026-07-14T10:00:00Z",
         "tags": ["db:default"], "paths": ["/default.sql"], "hostname": "web1"},
        {"id": "cccc3333dddd4444", "time": "2026-07-14T11:00:00Z"},
    ])
    first, second = restic.snapshots()
    assert first == Snapshot(
        id="aaaa1111bbbb2222", short_id="aaaa1111", time="2026-07-14T10:00:00Z",
        tags=["db:default"], paths=["/default.sql"], hostname="web1",
    )
    assert (second.tags, second.paths, second.short_id) == ([], [], "")


@pytest.mark.parametrize("stdout, expected", [
    ("restic 0.17.3 compiled with go1.23.1 on linux/amd64\n", (0, 17, 3)),
    ("restic 0.18.0-dev (compiled manually)\n", (0, 18, 0)),
    ("something unexpected\n", None),
])
def test_version_info(run, restic, stdout, expected):
    run.stdout = stdout
    assert restic.version_info() == expected
    assert run.argv == ["restic", "version"]


def test_snapshot_timestamp_orders_mixed_offsets_correctly():
    # 10:30+02:00 is 08:30 UTC: earlier than 09:00Z, though it sorts later as text.
    early = Snapshot(id="a", short_id="a", time="2026-07-14T10:30:00.123456789+02:00")
    late = Snapshot(id="b", short_id="b", time="2026-07-14T09:00:00Z")
    assert early.time > late.time
    assert max([early, late], key=lambda s: s.timestamp) is late


@pytest.mark.parametrize("value", [
    "2026-07-14T10:00:00Z",
    "2026-07-14T10:00:00.5+00:00",
    "2026-07-14T10:00:00.123456789-05:30",
])
def test_parse_time_accepts_restic_formats(value):
    assert restic_mod._parse_time(value).tzinfo is not None


def test_nonzero_exit_raises_restic_error(run, restic):
    run.returncode, run.stderr = 1, "Fatal: unable to open repository"
    with pytest.raises(ResticError) as info:
        restic.init()
    assert (info.value.returncode, info.value.stderr) == (1, run.stderr)
    assert str(info.value) == "restic exited with code 1: Fatal: unable to open repository"


@pytest.mark.parametrize("timeout, expected", [(60, 60), (0, None), (None, None)])
def test_timeout_is_passed_to_subprocess(run, timeout, expected):
    Restic(repository="/repo", binary="restic", timeout=timeout).unlock()
    assert run.kwargs["timeout"] == expected


def test_timeout_expired_raises_restic_error(monkeypatch):
    def expire(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(restic_mod.subprocess, "run", expire)
    with pytest.raises(ResticError, match="timed out after 5s"):
        Restic(repository="/repo", binary="restic", timeout=5).unlock()


def test_env_overlay_wins_over_inherited_environ(run, monkeypatch):
    monkeypatch.setenv("RESTIC_PASSWORD", "stale-shell-value")
    Restic(repository="/repo", binary="restic",
           extra_env={"RESTIC_PASSWORD": "configured"}).init()
    assert run.kwargs["env"]["RESTIC_PASSWORD"] == "configured"


def test_backup_extra_env_reaches_env_not_argv(run, restic):
    restic.backup_command(DUMP, stdin_filename="default.sql",
                          extra_env={"PGPASSWORD": "s3cr3t"})
    assert run.kwargs["env"]["PGPASSWORD"] == "s3cr3t"
    assert not any("s3cr3t" in arg or "PGPASSWORD" in arg for arg in run.argv)


def test_password_never_in_argv_or_error(run):
    run.returncode, run.stderr = 1, "Fatal: wrong password or no key found"
    restic = Restic(repository="/repo", binary="restic",
                    extra_env={"RESTIC_PASSWORD": "s3cr3t-value"})
    with pytest.raises(ResticError) as info:
        restic.init()
    assert "s3cr3t-value" not in run.argv
    assert "s3cr3t-value" not in str(info.value) + repr(info.value)
