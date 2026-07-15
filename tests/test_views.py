"""Tests for the staff web UI in :mod:`django_recovery.views`.

``services.list_snapshots`` and ``jobs.launch`` are patched so no real restic
binary or background thread is exercised — these tests assert access control,
job creation, confirmation guards, and the JSON status contract.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from django_recovery.models import BackupJob
from django_recovery.restic import Snapshot

pytestmark = pytest.mark.django_db


def _snapshot():
    return Snapshot(
        id="deadbeefdeadbeef",
        short_id="deadbeef",
        time="2026-07-14T12:00:00Z",
        tags=["db:default", "test"],
        paths=["/default.sql"],
        hostname="host",
    )


@pytest.fixture
def superuser():
    return get_user_model().objects.create_superuser(
        username="admin", email="admin@example.com", password="pw"
    )


@pytest.fixture
def normal_user():
    return get_user_model().objects.create_user(
        username="bob", email="bob@example.com", password="pw"
    )


@pytest.fixture(autouse=True)
def _patch_services():
    """Keep every test off real restic/threads by default."""
    with patch(
        "django_recovery.views.services.list_snapshots", return_value=[_snapshot()]
    ), patch("django_recovery.views.jobs.launch") as launch:
        yield launch


# --- access control -------------------------------------------------------


def test_anonymous_dashboard_redirects_to_login(client):
    resp = client.get(reverse("recovery:dashboard"))
    assert resp.status_code == 302
    assert "/accounts/login" in resp["Location"]


def test_authenticated_non_superuser_dashboard_forbidden(client, normal_user):
    client.force_login(normal_user)
    resp = client.get(reverse("recovery:dashboard"))
    assert resp.status_code == 403


def test_superuser_dashboard_ok_shows_snapshot(client, superuser):
    client.force_login(superuser)
    resp = client.get(reverse("recovery:dashboard"))
    assert resp.status_code == 200
    assert "deadbeef" in resp.content.decode()
    assert list(resp.context["snapshots"])[0].short_id == "deadbeef"


def test_anonymous_start_remove_redirects_to_login(client):
    resp = client.post(reverse("recovery:start_remove"))
    assert resp.status_code == 302
    assert "/accounts/login" in resp["Location"]


# --- backup ---------------------------------------------------------------


def test_start_backup_creates_job_and_redirects(client, superuser, _patch_services):
    client.force_login(superuser)
    resp = client.post(reverse("recovery:start_backup"), {"database": "default"})
    job = BackupJob.objects.get()
    assert job.job_type == "backup"
    assert job.database_alias == "default"
    assert job.created_by == superuser
    _patch_services.assert_called_once()
    assert resp.status_code == 302
    assert resp["Location"] == reverse("recovery:job_detail", args=[job.pk])


def test_start_backup_blocked_when_job_active(client, superuser, _patch_services):
    BackupJob.objects.create(job_type="backup", status="running")
    client.force_login(superuser)
    resp = client.post(reverse("recovery:start_backup"))
    assert resp.status_code == 200
    assert BackupJob.objects.count() == 1  # no new job
    _patch_services.assert_not_called()
    assert "already running" in resp.content.decode().lower()


def test_start_backup_get_not_allowed(client, superuser):
    client.force_login(superuser)
    resp = client.get(reverse("recovery:start_backup"))
    assert resp.status_code == 405


# --- restore --------------------------------------------------------------


def test_start_restore_confirm_mismatch_400_no_job(client, superuser, _patch_services):
    client.force_login(superuser)
    resp = client.post(
        reverse("recovery:start_restore"),
        {"snapshot_id": "deadbeef", "database": "default", "confirm_alias": "wrong"},
    )
    assert resp.status_code == 400
    assert BackupJob.objects.count() == 0
    _patch_services.assert_not_called()


def test_start_restore_confirmed_creates_job(client, superuser, _patch_services):
    client.force_login(superuser)
    resp = client.post(
        reverse("recovery:start_restore"),
        {
            "snapshot_id": "deadbeef",
            "database": "default",
            "confirm_alias": "default",
        },
    )
    job = BackupJob.objects.get()
    assert job.job_type == "restore"
    assert job.database_alias == "default"
    assert job.snapshot_id == "deadbeef"
    _patch_services.assert_called_once()
    assert resp.status_code == 302
    assert resp["Location"] == reverse("recovery:job_detail", args=[job.pk])


# --- remove ---------------------------------------------------------------


def test_start_remove_without_confirm_400_no_job(client, superuser, _patch_services):
    client.force_login(superuser)
    resp = client.post(
        reverse("recovery:start_remove"), {"snapshot_id": "deadbeef"}
    )
    assert resp.status_code == 400
    assert BackupJob.objects.count() == 0
    _patch_services.assert_not_called()


def test_start_remove_confirmed_creates_job(client, superuser, _patch_services):
    client.force_login(superuser)
    resp = client.post(
        reverse("recovery:start_remove"),
        {"snapshot_id": "deadbeef", "confirm": "on"},
    )
    job = BackupJob.objects.get()
    assert job.job_type == "remove"
    assert job.snapshot_id == "deadbeef"
    _patch_services.assert_called_once()
    assert resp.status_code == 302
    assert resp["Location"] == reverse("recovery:job_detail", args=[job.pk])


# --- job status -----------------------------------------------------------


def test_job_status_returns_json_with_log_tail(client, superuser):
    log = "\n".join(f"line {i}" for i in range(150)) + "\n"
    job = BackupJob.objects.create(job_type="backup", status="success", log=log)
    client.force_login(superuser)
    resp = client.get(reverse("recovery:job_status", args=[job.pk]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["finished"] is True
    tail_lines = data["log_tail"].splitlines()
    assert len(tail_lines) == 100  # last 100 lines only
    assert tail_lines[0] == "line 50"
    assert tail_lines[-1] == "line 149"


def test_job_status_running_not_finished(client, superuser):
    job = BackupJob.objects.create(job_type="backup", status="running", log="x\n")
    client.force_login(superuser)
    resp = client.get(reverse("recovery:job_status", args=[job.pk]))
    assert resp.json()["finished"] is False


def test_job_detail_renders(client, superuser):
    job = BackupJob.objects.create(job_type="backup", status="running", log="hello\n")
    client.force_login(superuser)
    resp = client.get(reverse("recovery:job_detail", args=[job.pk]))
    assert resp.status_code == 200
    assert "hello" in resp.content.decode()


# --- template rendering ---------------------------------------------------


def test_dashboard_template_renders_actions(client, superuser):
    client.force_login(superuser)
    resp = client.get(reverse("recovery:dashboard"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Backup now" in body
    assert "deadbeef" in body  # snapshot short_id
    assert "Restore" in body
    assert "Remove" in body


def test_job_detail_template_has_log_and_poll_script(client, superuser):
    job = BackupJob.objects.create(
        job_type="backup", status="running", log="streaming line\n"
    )
    client.force_login(superuser)
    resp = client.get(reverse("recovery:job_detail", args=[job.pk]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "streaming line" in body
    assert reverse("recovery:job_status", args=[job.pk]) in body
