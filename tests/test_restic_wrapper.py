"""Tests for the restic CLI wrapper.

All tests mock ``subprocess.run`` / ``subprocess.Popen`` and assert on the
exact argv list built by the wrapper. No real restic binary is required.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from django_recovery import restic as restic_mod
from django_recovery.restic import Restic, ResticError, Snapshot


def _ok(stdout="", stderr="", returncode=0):
    """A fake CompletedProcess-like object."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def mock_run(monkeypatch):
    """Patch subprocess.run inside the restic module; record the call."""
    calls = []

    def fake_run(argv, *args, **kwargs):
        calls.append(SimpleNamespace(args=(argv, *args), kwargs=kwargs))
        return _ok(stdout=fake_run.stdout, stderr=fake_run.stderr,
                   returncode=fake_run.returncode)

    fake_run.stdout = ""
    fake_run.stderr = ""
    fake_run.returncode = 0
    fake_run.calls = calls
    monkeypatch.setattr(restic_mod.subprocess, "run", fake_run)
    return fake_run


def test_backup_stdin_from_command_argv(mock_run):
    r = Restic(repository="/repo", binary="/usr/bin/restic")
    r.backup_command(
        ["pg_dump", "-d", "app"],
        stdin_filename="default.sql",
        tags=["db:default"],
    )
    argv = mock_run.calls[0].args[0]
    assert argv == [
        "/usr/bin/restic", "--json", "-r", "/repo", "backup",
        "--stdin-filename", "default.sql", "--tag", "db:default",
        "--stdin-from-command", "--", "pg_dump", "-d", "app",
    ]


def test_backup_command_no_tags(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.backup_command(["sqlite3", "db", ".dump"], stdin_filename="default.sql")
    argv = mock_run.calls[0].args[0]
    assert argv == [
        "restic", "--json", "-r", "/repo", "backup",
        "--stdin-filename", "default.sql",
        "--stdin-from-command", "--", "sqlite3", "db", ".dump",
    ]


def test_backup_command_merges_extra_env_without_argv_leak(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.backup_command(
        ["pg_dump", "-d", "app"],
        stdin_filename="default.sql",
        tags=["db:default"],
        extra_env={"PGPASSWORD": "s3cr3t"},
    )
    argv = mock_run.calls[0].args[0]
    env = mock_run.calls[0].kwargs["env"]
    # extra_env is merged into the subprocess environment...
    assert env["PGPASSWORD"] == "s3cr3t"
    # ...but never leaks into argv.
    assert "s3cr3t" not in argv
    assert "PGPASSWORD" not in argv


def test_backup_paths_argv(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.backup_paths(["/media"], tags=["media"])
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "backup", "/media",
                    "--tag", "media"]


def test_init_argv(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.init()
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "init"]


def test_is_initialized_argv_and_true_on_success(mock_run):
    r = Restic(repository="/repo", binary="restic")
    assert r.is_initialized() is True
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "cat", "config"]


def test_is_initialized_false_on_restic_error(mock_run):
    mock_run.returncode = 1
    mock_run.stderr = "Fatal: unable to open config file"
    r = Restic(repository="/repo", binary="restic")
    assert r.is_initialized() is False


def test_global_args_injected_after_repo(mock_run):
    r = Restic(repository="/repo", binary="restic",
               global_args=["--compression", "max", "--no-cache"])
    r.init()
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo",
                    "--compression", "max", "--no-cache", "init"]


def test_backup_flags_host_skip_read_concurrency(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.backup_command(
        ["sqlite3", "db", ".dump"],
        stdin_filename="default.sql",
        tags=["db:default"],
        host="web1",
        skip_if_unchanged=True,
        read_concurrency=4,
    )
    argv = mock_run.calls[0].args[0]
    assert argv == [
        "restic", "--json", "-r", "/repo", "backup",
        "--stdin-filename", "default.sql", "--tag", "db:default",
        "--host", "web1", "--skip-if-unchanged", "--read-concurrency", "4",
        "--stdin-from-command", "--", "sqlite3", "db", ".dump",
    ]


def test_backup_paths_exclude_patterns(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.backup_paths(["/media"], tags=["media"], exclude=["*.tmp", "cache/*"])
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "backup", "/media",
                    "--tag", "media", "--exclude", "*.tmp",
                    "--exclude", "cache/*"]


def test_forget_policy_full_argv(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.forget_policy(
        {"daily": 7, "weekly": 4, "last": 5, "within": "7d"},
    )
    argv = mock_run.calls[0].args[0]
    assert argv == [
        "restic", "--json", "-r", "/repo", "forget",
        "--group-by", "paths,tags",
        "--keep-last", "5", "--keep-daily", "7", "--keep-weekly", "4",
        "--keep-within", "7d", "--prune",
    ]


def test_forget_policy_dry_run_no_prune(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.forget_policy({"daily": 7}, prune=False, dry_run=True)
    argv = mock_run.calls[0].args[0]
    assert argv == [
        "restic", "--json", "-r", "/repo", "forget",
        "--group-by", "paths,tags", "--keep-daily", "7", "--dry-run",
    ]


def test_forget_snapshot_argv(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.forget_snapshot("abc123")
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "forget", "abc123",
                    "--prune"]


def test_forget_snapshot_no_prune(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.forget_snapshot("abc123", prune=False)
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "forget", "abc123"]


def test_unlock_argv(mock_run):
    r = Restic(repository="/repo", binary="restic")
    r.unlock()
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "unlock"]


def test_snapshots_parses_json(mock_run):
    payload = [
        {
            "id": "aaaa1111bbbb2222",
            "short_id": "aaaa1111",
            "time": "2026-07-14T10:00:00Z",
            "tags": ["db:default", "test"],
            "paths": ["/default.sql"],
            "hostname": "web1",
        },
        {
            "id": "cccc3333dddd4444",
            "short_id": "cccc3333",
            "time": "2026-07-14T11:00:00Z",
            "hostname": "web1",
        },
    ]
    mock_run.stdout = json.dumps(payload)
    r = Restic(repository="/repo", binary="restic")
    snaps = r.snapshots()
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "snapshots"]
    assert isinstance(snaps, list)
    assert all(isinstance(s, Snapshot) for s in snaps)
    assert snaps[0].id == "aaaa1111bbbb2222"
    assert snaps[0].short_id == "aaaa1111"
    assert snaps[0].tags == ["db:default", "test"]
    assert snaps[0].paths == ["/default.sql"]
    assert snaps[0].hostname == "web1"
    # missing tags/paths tolerated -> default []
    assert snaps[1].tags == []
    assert snaps[1].paths == []


def test_snapshots_with_tags_argv(mock_run):
    mock_run.stdout = "[]"
    r = Restic(repository="/repo", binary="restic")
    r.snapshots(tags=["db:default"])
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "snapshots",
                    "--tag", "db:default"]


def test_version_argv_and_return(mock_run):
    mock_run.stdout = "restic 0.19.1 compiled with go1.22\n"
    r = Restic(repository="/repo", binary="restic")
    out = r.version()
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "version"]
    assert out == "restic 0.19.1 compiled with go1.22"


def test_nonzero_exit_raises_resticerror_with_stderr(mock_run):
    mock_run.returncode = 1
    mock_run.stderr = "Fatal: unable to open repository"
    r = Restic(repository="/repo", binary="restic")
    with pytest.raises(ResticError) as exc_info:
        r.init()
    err = exc_info.value
    assert err.returncode == 1
    assert err.stderr == "Fatal: unable to open repository"
    assert "Fatal: unable to open repository" in str(err)
    assert "1" in str(err)


def test_env_overlay_wins_over_inherited_environ(mock_run, monkeypatch):
    monkeypatch.setenv("RESTIC_PASSWORD", "stale-shell-value")
    r = Restic(
        repository="/repo",
        extra_env={"RESTIC_PASSWORD": "backend-value"},
        binary="restic",
    )
    r.init()
    env = mock_run.calls[0].kwargs["env"]
    # The backend-provided overlay beats whatever the shell had.
    assert env["RESTIC_PASSWORD"] == "backend-value"


def test_env_sets_password_file(mock_run):
    r = Restic(
        repository="/repo",
        extra_env={"RESTIC_PASSWORD_FILE": "/etc/restic.pass"},
        binary="restic",
    )
    r.init()
    env = mock_run.calls[0].kwargs["env"]
    assert env["RESTIC_PASSWORD_FILE"] == "/etc/restic.pass"


def test_password_never_in_argv_or_error_string(mock_run):
    mock_run.returncode = 1
    mock_run.stderr = "Fatal: wrong password or no key found"
    r = Restic(
        repository="/repo",
        extra_env={"RESTIC_PASSWORD": "s3cr3t-value"},
        binary="restic",
    )
    with pytest.raises(ResticError) as exc_info:
        r.init()
    argv = mock_run.calls[0].args[0]
    assert "s3cr3t-value" not in argv
    assert "s3cr3t-value" not in str(exc_info.value)
    assert "s3cr3t-value" not in repr(exc_info.value)


def test_dump_popen_no_json_and_stdout_pipe(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, argv, *args, **kwargs):
            calls.append(SimpleNamespace(argv=argv, kwargs=kwargs))
            self.stdout = object()

    monkeypatch.setattr(restic_mod.subprocess, "Popen", FakePopen)
    r = Restic(repository="/repo", binary="restic")
    proc = r.dump_popen("latest", "default.sql")
    assert isinstance(proc, FakePopen)
    argv = calls[0].argv
    assert "--json" not in argv
    assert argv == ["restic", "-r", "/repo", "dump", "latest", "default.sql"]
    assert calls[0].kwargs["stdout"] is subprocess.PIPE
    assert "env" in calls[0].kwargs


# --- review fixes: time parsing, id lookup, timeout, version ----------------------

def test_snapshot_timestamp_orders_mixed_offsets_correctly():
    # 10:30+02:00 is 08:30 UTC, i.e. *earlier* than 09:00Z, though it sorts
    # later as a string.
    early = Snapshot(id="a", short_id="a", time="2026-07-14T10:30:00.123456789+02:00")
    late = Snapshot(id="b", short_id="b", time="2026-07-14T09:00:00Z")
    assert early.time > late.time  # the old string comparison got this wrong
    assert max([early, late], key=lambda s: s.timestamp) is late


@pytest.mark.parametrize("value", [
    "2026-07-14T10:00:00Z",
    "2026-07-14T10:00:00.5+00:00",
    "2026-07-14T10:00:00.123456789-05:30",
])
def test_parse_time_accepts_restic_formats(value):
    assert restic_mod._parse_time(value).tzinfo is not None


def test_snapshots_with_ids_argv(mock_run):
    mock_run.stdout = "[]"
    Restic(repository="/repo", binary="restic").snapshots(snapshot_ids=["abc123"])
    argv = mock_run.calls[0].args[0]
    assert argv == ["restic", "--json", "-r", "/repo", "snapshots", "abc123"]


def test_timeout_is_passed_to_subprocess(mock_run):
    Restic(repository="/repo", binary="restic", timeout=60).unlock()
    assert mock_run.calls[0].kwargs["timeout"] == 60


def test_no_timeout_by_default(mock_run):
    Restic(repository="/repo", binary="restic", timeout=0).unlock()
    assert mock_run.calls[0].kwargs["timeout"] is None


def test_timeout_expired_raises_restic_error(monkeypatch):
    def fake_run(argv, *args, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(restic_mod.subprocess, "run", fake_run)
    with pytest.raises(ResticError, match="timed out after 5s"):
        Restic(repository="/repo", binary="restic", timeout=5).unlock()


@pytest.mark.parametrize("stdout, expected", [
    ("restic 0.17.3 compiled with go1.23.1 on linux/amd64\n", (0, 17, 3)),
    ("restic 0.18.0-dev (compiled manually)\n", (0, 18, 0)),
    ("something unexpected\n", None),
])
def test_version_info(mock_run, stdout, expected):
    mock_run.stdout = stdout
    assert Restic(repository="/repo", binary="restic").version_info() == expected
