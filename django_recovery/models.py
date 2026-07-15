"""The :class:`BackupJob` model backing the web UI's async operations.

Every UI-triggered operation (backup/restore/remove/init) is recorded as a
``BackupJob`` row. A background thread updates the row's ``status`` and
appends progress to ``log`` as it runs, and the UI polls the row for live
status. ``has_active`` lets the runner serialize operations — restic repo
locking makes concurrent operations from one host pointless.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class JobType(models.TextChoices):
    BACKUP = "backup", "Backup"
    RESTORE = "restore", "Restore"
    REMOVE = "remove", "Remove"
    INIT = "init", "Init"


class JobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class BackupJob(models.Model):
    job_type = models.CharField(max_length=20, choices=JobType.choices)
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    log = models.TextField(blank=True, default="")
    database_alias = models.CharField(max_length=255, blank=True, default="")
    snapshot_id = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.job_type} #{self.pk} ({self.status})"

    def append_log(self, text):
        """Append ``text`` (with a trailing newline) to ``log`` and persist."""
        if not text.endswith("\n"):
            text += "\n"
        self.log += text
        self.save(update_fields=["log"])

    def mark_running(self):
        self.status = JobStatus.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_done(self, ok: bool):
        self.status = JobStatus.SUCCESS if ok else JobStatus.FAILED
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at"])

    @classmethod
    def has_active(cls) -> bool:
        return cls.objects.filter(
            status__in=[JobStatus.PENDING, JobStatus.RUNNING]
        ).exists()
