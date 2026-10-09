"""The actual backup operations, shared by the management command and your own code.

Each function takes an optional ``log_callback`` that receives short progress
messages (the command prints them). Passwords never reach the callback.
Call these directly from Celery tasks or anywhere else you schedule work.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from .conf import RecoveryConfig, build_global_args, get_config, resolve_binary
from .connectors import get_connector
from .restic import Restic, Snapshot

LogCallback = Callable[[str], None]

# 0.16 added --stdin-from-command, which every database backup relies on.
MIN_RESTIC_VERSION = (0, 16, 0)


def _noop(_message: str) -> None:
    pass


def _make_restic(config: RecoveryConfig | None = None) -> Restic:
    config = config or get_config()
    return Restic(
        config.repository.url,
        extra_env=config.restic_env(),
        binary=resolve_binary(config),
        global_args=build_global_args(config),
        timeout=config.tuning.get("timeout"),
    )


def run_init(
    config: RecoveryConfig | None = None,
    log_callback: LogCallback = _noop,
) -> None:
    """Create the restic repository, or do nothing if it already exists.

    Also checks the restic version, so an old binary is reported now rather
    than as a confusing failure on the first backup.
    """
    restic = _make_restic(config)
    version = restic.version_info()
    if version is not None and version < MIN_RESTIC_VERSION:
        raise RuntimeError(
            f"restic {'.'.join(map(str, version))} is too old; django-recovery "
            f"needs {'.'.join(map(str, MIN_RESTIC_VERSION))} or newer."
        )
    if restic.is_initialized():
        log_callback("Repository already initialized; skipping.")
        return
    log_callback("Initializing repository...")
    restic.init()
    log_callback("Repository initialized.")


def run_backup(
    databases: list[str] | None = None,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback = _noop,
) -> dict[str, str]:
    """Back up each database, plus media files if ``MEDIA`` is on.

    restic runs each database's dump command and saves its output. The
    connector's credentials (``PGPASSWORD`` and friends) are handed to restic
    so the dump can log in. Returns ``{"default": "ok", ...}``.
    """
    config = config or get_config()
    restic = _make_restic(config)
    databases = databases if databases is not None else config.databases
    read_concurrency = config.tuning.get("read_concurrency")

    summary: dict[str, str] = {}
    for alias in databases:
        log_callback(f"Backing up database '{alias}'...")
        conn = get_connector(alias)
        restic.backup_command(
            conn.dump_command(),
            stdin_filename=conn.stdin_filename,
            tags=[f"db:{alias}", *config.tags],
            extra_env=conn.extra_env(),
            host=config.host,
            skip_if_unchanged=config.skip_if_unchanged,
            read_concurrency=read_concurrency,
        )
        summary[alias] = "ok"
        log_callback(f"Database '{alias}' backed up.")

    if config.media:
        from django.conf import settings

        log_callback("Backing up media...")
        restic.backup_paths(
            [settings.MEDIA_ROOT],
            tags=["media", *config.tags],
            host=config.host,
            skip_if_unchanged=config.skip_if_unchanged,
            read_concurrency=read_concurrency,
            exclude=config.media_exclude,
        )
        summary["media"] = "ok"
        log_callback("Media backed up.")

    return summary


def run_restore(
    alias: str,
    snapshot_id: str,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback = _noop,
) -> None:
    """Replace database ``alias`` with the contents of ``snapshot_id``.

    ``snapshot_id`` can be a full id, a prefix, or ``"latest"`` (the newest
    backup of this database). The snapshot must be labelled ``db:<alias>``, so
    you can't load one database's backup into another by mistake. restic
    streams the backup straight into the restore client, and both must
    succeed.
    """
    config = config or get_config()
    restic = _make_restic(config)
    db_tag = f"db:{alias}"

    log_callback(f"Resolving snapshot '{snapshot_id}' for database '{alias}'...")
    # Only fetch the snapshots we might use. An explicit id is looked up
    # without the tag filter on purpose: if it belongs to another database,
    # the user gets "not a backup of database X" instead of "not found".
    if snapshot_id == "latest":
        snapshots = restic.snapshots(tags=[db_tag])
    else:
        snapshots = restic.snapshots(snapshot_ids=[snapshot_id])

    snapshot = _resolve_snapshot(snapshots, snapshot_id, db_tag)
    if snapshot is None:
        raise ValueError(f"snapshot {snapshot_id} not found")
    if db_tag not in snapshot.tags:
        raise ValueError(
            f"snapshot {snapshot.short_id or snapshot.id} is not a backup of "
            f"database '{alias}'"
        )

    conn = get_connector(alias)
    log_callback(f"Restoring database '{alias}' from snapshot {snapshot.short_id}...")
    proc = restic.dump_popen(snapshot.id, conn.stdin_filename)
    try:
        result = subprocess.run(
            conn.restore_command(),
            stdin=proc.stdout,
            env={**os.environ, **conn.extra_env()},
        )
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            f"restic dump failed for snapshot {snapshot.short_id} "
            f"(exit code {proc.returncode})"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"restore of database '{alias}' failed "
            f"(exit code {result.returncode})"
        )
    log_callback(f"Database '{alias}' restored.")


def _resolve_snapshot(
    snapshots: list[Snapshot],
    snapshot_id: str,
    db_tag: str,
) -> Snapshot | None:
    if snapshot_id == "latest":
        candidates = [s for s in snapshots if db_tag in s.tags]
        return max(candidates, key=lambda s: s.timestamp) if candidates else None
    for s in snapshots:
        if s.id.startswith(snapshot_id) or snapshot_id == s.short_id:
            return s
    return None


def remove_snapshot(
    snapshot_id: str,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback = _noop,
) -> None:
    """Delete one snapshot and free the space only it was using."""
    restic = _make_restic(config)
    log_callback(f"Removing snapshot {snapshot_id}...")
    restic.forget_snapshot(snapshot_id, prune=True)
    log_callback(f"Snapshot {snapshot_id} removed.")


def run_prune(
    config: RecoveryConfig | None = None,
    dry_run: bool = False,
    log_callback: LogCallback = _noop,
) -> None:
    """Delete snapshots that fall outside ``RECOVERY['RETENTION']``.

    Raises ``ValueError`` if no policy is set: without one, there is nothing
    sensible to keep or delete.
    """
    config = config or get_config()
    if not config.retention:
        raise ValueError(
            "RECOVERY['RETENTION'] is not configured; nothing to prune. "
            "Add a retention policy, e.g. {'daily': 7, 'weekly': 4}."
        )
    restic = _make_restic(config)
    policy = ", ".join(f"{k}={v}" for k, v in sorted(config.retention.items()))
    verb = "Previewing" if dry_run else "Applying"
    log_callback(f"{verb} retention policy ({policy})...")
    restic.forget_policy(config.retention, prune=not dry_run, dry_run=dry_run)
    log_callback("Retention preview complete." if dry_run else "Retention policy applied.")


def list_snapshots(
    config: RecoveryConfig | None = None,
    log_callback: LogCallback = _noop,
) -> list[Snapshot]:
    """Every snapshot in the repository."""
    restic = _make_restic(config)
    log_callback("Listing snapshots...")
    return restic.snapshots()
