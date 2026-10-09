"""A small wrapper that builds restic commands and runs them.

Nothing here touches backup data. It assembles the argument list, runs the
restic binary, and turns failures into ``ResticError``. Passwords and cloud
keys travel in the process environment (``extra_env``), never in the argument
list or an error message, so they can't leak through ``ps`` or a log.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime


class ResticError(RuntimeError):
    """restic exited with a non-zero code.

    Keeps the ``returncode`` and restic's ``stderr``. The message never
    includes the environment, so it is safe to show or log.
    """

    def __init__(self, returncode: int, stderr: str):
        self.returncode = returncode
        self.stderr = stderr or ""
        super().__init__(f"restic exited with code {returncode}: {self.stderr}")


_FRACTION = re.compile(r"\.(\d+)")


def _parse_time(value: str) -> datetime:
    """Parse a restic timestamp such as ``2026-07-14T10:00:00.123456789+02:00``.

    Python 3.10's ``fromisoformat`` can't handle a trailing ``Z`` or more than
    six fractional digits, so we tidy both up first.
    """
    value = value.replace("Z", "+00:00")
    value = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), value, count=1)
    return datetime.fromisoformat(value)


@dataclass
class Snapshot:
    """One snapshot, as listed by ``restic snapshots --json``."""

    id: str
    short_id: str
    time: str
    tags: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    hostname: str = ""

    @classmethod
    def from_json(cls, d: dict) -> Snapshot:
        # restic leaves out empty lists, so missing tags/paths become [].
        return cls(
            id=d.get("id", ""),
            short_id=d.get("short_id", ""),
            time=d.get("time", ""),
            tags=list(d.get("tags") or []),
            paths=list(d.get("paths") or []),
            hostname=d.get("hostname", ""),
        )

    @property
    def timestamp(self) -> datetime:
        """``time`` as a real datetime, so snapshots from different timezones sort correctly."""
        return _parse_time(self.time)


class Restic:
    """Runs restic commands against one repository."""

    def __init__(
        self,
        repository: str,
        extra_env: dict[str, str] | None = None,
        binary: str = "restic",
        global_args: list[str] | None = None,
        timeout: int | None = None,
    ):
        self.repository = repository
        self.extra_env = dict(extra_env or {})
        self.binary = binary
        self.global_args = list(global_args or [])
        # Seconds before a restic call is stopped. None or 0 means wait forever.
        self.timeout = timeout or None

    def _base_argv(self) -> list[str]:
        return [self.binary, "--json", "-r", self.repository, *self.global_args]

    def _env(self) -> dict[str, str]:
        # Our values win over whatever the shell happened to export, so a stale
        # RESTIC_PASSWORD in someone's terminal can't change the result.
        env = os.environ.copy()
        env.update(self.extra_env)
        return env

    def _run(
        self,
        argv: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        env = self._env()
        if extra_env:
            env.update(extra_env)
        try:
            proc = subprocess.run(
                argv,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # subprocess.run has already killed restic. That can leave a stale
            # lock behind, which `restic unlock` clears.
            raise ResticError(
                -1, f"timed out after {self.timeout}s (TUNING['timeout'])"
            ) from exc
        if proc.returncode != 0:
            raise ResticError(proc.returncode, proc.stderr)
        return proc

    def init(self) -> subprocess.CompletedProcess:
        return self._run(self._base_argv() + ["init"])

    def is_initialized(self) -> bool:
        """Whether the repository exists and can be opened.

        Any failure counts as "no": missing repository, unreachable storage, or
        a wrong password. If the repository does exist, the following ``init``
        fails with restic's real error message.
        """
        try:
            self._run(self._base_argv() + ["cat", "config"])
        except ResticError:
            return False
        return True

    def _backup_flags(
        self,
        tags: list[str] | None,
        host: str | None,
        skip_if_unchanged: bool,
        read_concurrency: int | None,
    ) -> list[str]:
        argv: list[str] = []
        for tag in tags or []:
            argv += ["--tag", tag]
        if host:
            argv += ["--host", host]
        if skip_if_unchanged:
            argv += ["--skip-if-unchanged"]
        if read_concurrency:
            argv += ["--read-concurrency", str(read_concurrency)]
        return argv

    def backup_command(
        self,
        cmd: list[str],
        stdin_filename: str,
        tags: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
        host: str | None = None,
        skip_if_unchanged: bool = False,
        read_concurrency: int | None = None,
    ) -> subprocess.CompletedProcess:
        """Run ``cmd`` and save what it prints as a file named ``stdin_filename``.

        restic runs the command itself (``--stdin-from-command``), so if the
        dump fails, no snapshot is created. Because the dump runs inside
        restic's process, anything it needs, such as ``PGPASSWORD``, goes in
        ``extra_env`` for this call.
        """
        argv = self._base_argv() + ["backup", "--stdin-filename", stdin_filename]
        argv += self._backup_flags(tags, host, skip_if_unchanged, read_concurrency)
        argv += ["--stdin-from-command", "--"] + cmd
        return self._run(argv, extra_env=extra_env)

    def backup_paths(
        self,
        paths: list[str],
        tags: list[str] | None = None,
        host: str | None = None,
        skip_if_unchanged: bool = False,
        read_concurrency: int | None = None,
        exclude: list[str] | None = None,
    ) -> subprocess.CompletedProcess:
        argv = self._base_argv() + ["backup"] + list(paths)
        argv += self._backup_flags(tags, host, skip_if_unchanged, read_concurrency)
        for pattern in exclude or []:
            argv += ["--exclude", pattern]
        return self._run(argv)

    def snapshots(
        self,
        tags: list[str] | None = None,
        snapshot_ids: list[str] | None = None,
    ) -> list[Snapshot]:
        """List snapshots, optionally only those with ``tags`` or matching ``snapshot_ids``.

        Like restic itself, ids may be shortened to a prefix.
        """
        argv = self._base_argv() + ["snapshots"]
        for tag in tags or []:
            argv += ["--tag", tag]
        argv += list(snapshot_ids or [])
        proc = self._run(argv)
        data = json.loads(proc.stdout or "[]")
        return [Snapshot.from_json(d) for d in data]

    def forget_snapshot(
        self,
        snapshot_id: str,
        prune: bool = True,
    ) -> subprocess.CompletedProcess:
        argv = self._base_argv() + ["forget", snapshot_id]
        if prune:
            argv += ["--prune"]
        return self._run(argv)

    # RETENTION key -> restic flag, in a fixed order so the command is predictable.
    _POLICY_FLAGS = (
        ("last", "--keep-last"),
        ("hourly", "--keep-hourly"),
        ("daily", "--keep-daily"),
        ("weekly", "--keep-weekly"),
        ("monthly", "--keep-monthly"),
        ("yearly", "--keep-yearly"),
        ("within", "--keep-within"),
    )

    def forget_policy(
        self,
        retention: dict,
        prune: bool = True,
        group_by: str = "paths,tags",
        dry_run: bool = False,
    ) -> subprocess.CompletedProcess:
        """Delete snapshots outside the ``retention`` policy.

        We group by ``paths,tags`` instead of restic's default ``host,paths``.
        That keeps each database and the media files on their own count, and a
        container that gets a new hostname on every deploy doesn't start a new
        group each time.
        """
        argv = self._base_argv() + ["forget", "--group-by", group_by]
        for key, flag in self._POLICY_FLAGS:
            value = retention.get(key)
            if value:
                argv += [flag, str(value)]
        if dry_run:
            argv += ["--dry-run"]
        if prune:
            argv += ["--prune"]
        return self._run(argv)

    def dump_popen(self, snapshot_id: str, path: str) -> subprocess.Popen:
        """Start streaming ``path`` from a snapshot to stdout.

        No ``--json`` here: ``restic dump`` writes the raw file bytes, and JSON
        output would corrupt them. The caller reads ``proc.stdout`` and must
        wait for the process to finish.
        """
        argv = [self.binary, "-r", self.repository, *self.global_args,
                "dump", snapshot_id, path]
        return subprocess.Popen(argv, stdout=subprocess.PIPE, env=self._env())

    def unlock(self) -> subprocess.CompletedProcess:
        return self._run(self._base_argv() + ["unlock"])

    def version(self) -> str:
        proc = self._run([self.binary, "version"])
        return proc.stdout.strip()

    def version_info(self) -> tuple[int, int, int] | None:
        """restic's version as ``(major, minor, patch)``, or None if we can't tell."""
        match = re.search(r"restic (\d+)\.(\d+)\.(\d+)", self.version())
        if match is None:
            return None
        major, minor, patch = (int(part) for part in match.groups())
        return major, minor, patch
