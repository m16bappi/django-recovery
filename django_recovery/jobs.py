"""Background runner that executes a :class:`BackupJob` in a daemon thread.

The web UI creates a ``BackupJob`` row and calls :func:`launch`, which spawns a
daemon thread that runs the corresponding service function and streams progress
back into the row's ``log`` while updating its ``status``. Only one operation
may run at a time — restic repo locking makes concurrent operations from one
host pointless — so :func:`launch` refuses to start when another job is already
pending or running.
"""

import threading

from django.db import close_old_connections

from django_recovery import services
from django_recovery.models import BackupJob


class JobAlreadyRunning(RuntimeError):
    """Raised by :func:`launch` when another job is already active."""


def launch(job: BackupJob) -> threading.Thread:
    """Start ``job`` in a daemon thread, returning the thread.

    Refuses (raising :class:`JobAlreadyRunning`) when a *different* job is
    already pending or running. The passed-in ``job`` is excluded from that
    check so a caller may create-then-launch without self-colliding.
    """
    others_active = (
        BackupJob.objects.filter(status__in=["pending", "running"])
        .exclude(pk=job.pk)
        .exists()
    )
    if others_active:
        raise JobAlreadyRunning("Another backup job is already running.")

    thread = threading.Thread(target=_run_job, args=(job.pk,), daemon=True)
    thread.start()
    return thread


def _run_job(job_pk: int) -> None:
    """Execute the job identified by ``job_pk`` (runs inside the worker thread)."""
    close_old_connections()
    try:
        job = BackupJob.objects.get(pk=job_pk)
        job.mark_running()
        try:
            if job.job_type == "backup":
                services.run_backup(
                    databases=[job.database_alias] if job.database_alias else None,
                    log_callback=job.append_log,
                )
            elif job.job_type == "restore":
                services.run_restore(
                    alias=job.database_alias,
                    snapshot_id=job.snapshot_id,
                    log_callback=job.append_log,
                )
            elif job.job_type == "remove":
                services.remove_snapshot(
                    job.snapshot_id,
                    log_callback=job.append_log,
                )
            elif job.job_type == "init":
                services.run_init(log_callback=job.append_log)
            else:
                raise ValueError(f"Unknown job type: {job.job_type!r}")
        except Exception as e:  # noqa: BLE001 — record failure, never crash thread
            job.append_log(f"ERROR: {e}")
            job.mark_done(False)
        else:
            job.mark_done(True)
    finally:
        close_old_connections()
