"""Tests for the :class:`BackupJob` model and its helper methods."""

import pytest
from django.contrib.auth import get_user_model

from django_recovery.models import BackupJob


@pytest.mark.django_db
def test_default_status_is_pending():
    job = BackupJob.objects.create(job_type="backup")
    assert job.status == "pending"


@pytest.mark.django_db
def test_append_log_adds_trailing_newline_and_persists():
    job = BackupJob.objects.create(job_type="backup")
    job.append_log("line1")
    job.append_log("line2")
    assert job.log == "line1\nline2\n"

    job.refresh_from_db()
    assert job.log == "line1\nline2\n"


@pytest.mark.django_db
def test_append_log_keeps_single_newline_when_already_present():
    job = BackupJob.objects.create(job_type="backup")
    job.append_log("already\n")
    assert job.log == "already\n"


@pytest.mark.django_db
def test_mark_running_sets_status_and_started_at():
    job = BackupJob.objects.create(job_type="backup")
    job.mark_running()
    assert job.status == "running"
    assert job.started_at is not None


@pytest.mark.django_db
def test_mark_done_success_and_failure():
    ok_job = BackupJob.objects.create(job_type="backup")
    ok_job.mark_done(True)
    assert ok_job.status == "success"
    assert ok_job.finished_at is not None

    bad_job = BackupJob.objects.create(job_type="backup")
    bad_job.mark_done(False)
    assert bad_job.status == "failed"
    assert bad_job.finished_at is not None


@pytest.mark.django_db
def test_has_active():
    assert BackupJob.has_active() is False

    pending = BackupJob.objects.create(job_type="backup", status="pending")
    assert BackupJob.has_active() is True
    pending.delete()

    running = BackupJob.objects.create(job_type="backup", status="running")
    assert BackupJob.has_active() is True
    running.delete()

    BackupJob.objects.create(job_type="backup", status="success")
    BackupJob.objects.create(job_type="restore", status="failed")
    assert BackupJob.has_active() is False


@pytest.mark.django_db
def test_created_by_is_nullable():
    job = BackupJob.objects.create(job_type="backup")
    assert job.created_by is None


@pytest.mark.django_db
def test_created_by_can_be_set():
    user = get_user_model().objects.create_user(username="admin", password="pw")
    job = BackupJob.objects.create(job_type="backup", created_by=user)
    job.refresh_from_db()
    assert job.created_by == user


@pytest.mark.django_db
def test_str_representation():
    job = BackupJob.objects.create(job_type="backup")
    assert str(job) == f"backup #{job.pk} (pending)"
