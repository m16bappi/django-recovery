"""Tests for the background job runner in :mod:`django_recovery.jobs`."""

from unittest.mock import Mock

import pytest

from django_recovery import jobs, services
from django_recovery.jobs import JobAlreadyRunning, _run_job, launch
from django_recovery.models import BackupJob


@pytest.mark.django_db
def test_run_job_backup_success(monkeypatch):
    def stub(databases=None, log_callback=None):
        log_callback("done")
        return {"db": "ok"}

    monkeypatch.setattr(services, "run_backup", stub)

    job = BackupJob.objects.create(job_type="backup", database_alias="db")
    _run_job(job.pk)

    job.refresh_from_db()
    assert job.status == "success"
    assert job.started_at is not None
    assert job.finished_at is not None
    assert "done" in job.log


@pytest.mark.django_db
def test_run_job_dispatches_backup_with_databases(monkeypatch):
    calls = {}

    def stub(databases=None, log_callback=None):
        calls["databases"] = databases

    monkeypatch.setattr(services, "run_backup", stub)

    job = BackupJob.objects.create(job_type="backup", database_alias="default")
    _run_job(job.pk)

    assert calls["databases"] == ["default"]


@pytest.mark.django_db
def test_run_job_backup_without_alias_passes_none(monkeypatch):
    calls = {}

    def stub(databases=None, log_callback=None):
        calls["databases"] = databases

    monkeypatch.setattr(services, "run_backup", stub)

    job = BackupJob.objects.create(job_type="backup", database_alias="")
    _run_job(job.pk)

    assert calls["databases"] is None


@pytest.mark.django_db
def test_run_job_dispatches_restore(monkeypatch):
    calls = {}

    def stub(alias=None, snapshot_id=None, log_callback=None):
        calls["alias"] = alias
        calls["snapshot_id"] = snapshot_id

    monkeypatch.setattr(services, "run_restore", stub)

    job = BackupJob.objects.create(
        job_type="restore", database_alias="default", snapshot_id="abc123"
    )
    _run_job(job.pk)

    assert calls == {"alias": "default", "snapshot_id": "abc123"}


@pytest.mark.django_db
def test_run_job_dispatches_remove(monkeypatch):
    calls = {}

    def stub(snapshot_id, log_callback=None):
        calls["snapshot_id"] = snapshot_id

    monkeypatch.setattr(services, "remove_snapshot", stub)

    job = BackupJob.objects.create(job_type="remove", snapshot_id="deadbeef")
    _run_job(job.pk)

    assert calls["snapshot_id"] == "deadbeef"


@pytest.mark.django_db
def test_run_job_dispatches_init(monkeypatch):
    calls = {}

    def stub(log_callback=None):
        calls["called"] = True

    monkeypatch.setattr(services, "run_init", stub)

    job = BackupJob.objects.create(job_type="init")
    _run_job(job.pk)

    assert calls["called"] is True
    job.refresh_from_db()
    assert job.status == "success"


@pytest.mark.django_db
def test_run_job_service_raising_marks_failed(monkeypatch):
    def stub(databases=None, log_callback=None):
        raise RuntimeError("boom happened")

    monkeypatch.setattr(services, "run_backup", stub)

    job = BackupJob.objects.create(job_type="backup")
    _run_job(job.pk)  # must not raise

    job.refresh_from_db()
    assert job.status == "failed"
    assert job.finished_at is not None
    assert "ERROR:" in job.log
    assert "boom happened" in job.log


@pytest.mark.django_db
def test_launch_raises_when_other_active_job_exists(monkeypatch):
    monkeypatch.setattr(jobs, "_run_job", lambda pk: None)

    BackupJob.objects.create(job_type="backup", status="running")
    job = BackupJob.objects.create(job_type="backup", status="pending")

    with pytest.raises(JobAlreadyRunning):
        launch(job)


@pytest.mark.django_db
def test_launch_does_not_raise_for_self(monkeypatch):
    monkeypatch.setattr(jobs, "_run_job", lambda pk: None)

    job = BackupJob.objects.create(job_type="backup", status="pending")

    thread = launch(job)
    thread.join(timeout=5)
    assert not thread.is_alive()


@pytest.mark.django_db
def test_run_job_closes_old_connections(monkeypatch):
    def stub(databases=None, log_callback=None):
        return {}

    monkeypatch.setattr(services, "run_backup", stub)
    mock_close = Mock()
    monkeypatch.setattr(jobs, "close_old_connections", mock_close)

    job = BackupJob.objects.create(job_type="backup")
    _run_job(job.pk)

    assert mock_close.called
