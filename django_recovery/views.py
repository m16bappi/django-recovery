"""Staff web UI exposing the four recovery operations.

Every view requires ``is_superuser`` (backups are credentials-grade power).
The dashboard *shows* snapshots and recent jobs; the three POST endpoints
*backup*, *restore*, and *remove* create a :class:`BackupJob` and hand it to
the background runner. All configuration comes from ``settings.RECOVERY`` —
the UI never accepts repository/credential configuration.
"""

from __future__ import annotations

import functools

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import jobs, services
from .conf import get_config
from .models import BackupJob


def superuser_required(view):
    """Require an authenticated superuser.

    Anonymous users are redirected to the login page (matching Django's
    ``user_passes_test`` default); authenticated non-superusers get a hard
    ``403`` rather than a login redirect, since logging in as themselves would
    not grant access.
    """

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _render_dashboard(request, message=None, status=200):
    """Render the dashboard, optionally with an inline ``message`` banner.

    Snapshot listing talks to restic, which can fail (missing repo, network,
    lock); on error the dashboard still renders with an empty snapshot list and
    the error surfaced as the banner message.
    """
    error = None
    try:
        snapshots = services.list_snapshots()
    except Exception as exc:  # noqa: BLE001 — surface, don't 500 the dashboard
        snapshots = []
        error = f"Could not list snapshots: {exc}"

    try:
        databases = get_config().databases
    except Exception:  # noqa: BLE001
        databases = []

    context = {
        "snapshots": snapshots,
        "recent_jobs": BackupJob.objects.all()[:20],
        "databases": databases,
        "active": BackupJob.has_active(),
        "message": message,
        "error": error,
    }
    return render(request, "django_recovery/dashboard.html", context, status=status)


@superuser_required
def dashboard(request):
    """Show snapshots, recent jobs, and the action controls."""
    return _render_dashboard(request)


@superuser_required
@require_POST
def start_backup(request):
    """Create and launch a backup job (unless one is already running)."""
    if BackupJob.has_active():
        return _render_dashboard(request, message="A job is already running.")

    job = BackupJob.objects.create(
        job_type="backup",
        database_alias=request.POST.get("database", ""),
        created_by=request.user,
    )
    jobs.launch(job)
    return redirect("recovery:job_detail", pk=job.pk)


@superuser_required
@require_POST
def start_restore(request):
    """Create and launch a restore job after confirming the target alias."""
    snapshot_id = request.POST.get("snapshot_id", "")
    database = request.POST.get("database", "")
    confirm_alias = request.POST.get("confirm_alias")

    if confirm_alias != database:
        return _render_dashboard(
            request,
            message=(
                "Restore not confirmed: the typed alias must match the "
                "selected database."
            ),
            status=400,
        )

    if BackupJob.has_active():
        return _render_dashboard(request, message="A job is already running.")

    job = BackupJob.objects.create(
        job_type="restore",
        database_alias=database,
        snapshot_id=snapshot_id,
        created_by=request.user,
    )
    jobs.launch(job)
    return redirect("recovery:job_detail", pk=job.pk)


@superuser_required
@require_POST
def start_remove(request):
    """Create and launch a snapshot-removal job after explicit confirmation."""
    snapshot_id = request.POST.get("snapshot_id", "")
    confirm = request.POST.get("confirm")

    if not confirm:
        return _render_dashboard(
            request,
            message="Removal not confirmed: check the confirmation box.",
            status=400,
        )

    if BackupJob.has_active():
        return _render_dashboard(request, message="A job is already running.")

    job = BackupJob.objects.create(
        job_type="remove",
        snapshot_id=snapshot_id,
        created_by=request.user,
    )
    jobs.launch(job)
    return redirect("recovery:job_detail", pk=job.pk)


@superuser_required
def job_detail(request, pk):
    """Render the live log/status page for a single job."""
    job = get_object_or_404(BackupJob, pk=pk)
    return render(request, "django_recovery/job_detail.html", {"job": job})


@superuser_required
def job_status(request, pk):
    """Return the job's status and the last 100 log lines as JSON."""
    job = get_object_or_404(BackupJob, pk=pk)
    return JsonResponse(
        {
            "status": job.status,
            "log_tail": "\n".join(job.log.splitlines()[-100:]),
            "finished": job.status in ("success", "failed"),
        }
    )
