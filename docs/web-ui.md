# Web dashboard

A superuser-only dashboard exposes exactly four operations — **show snapshots, backup,
restore, remove** — with zero configuration surface (everything comes from
`settings.RECOVERY`).

## Mounting

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path("recovery/", include("django_recovery.urls")),
]
```

Then visit `/recovery/` as a superuser.

## Access control

Strict by design: anonymous users are redirected to login, and authenticated
**non-superusers get a hard 403**. Backups are credentials-grade power, so `is_staff`
is deliberately not enough.

## The four operations

- **Show** — the dashboard lists snapshots (id, time, tags, paths) and recent jobs.
- **Backup** — a single "Backup now" button launches a backup job.
- **Restore** — a per-snapshot form requires you to type the target alias into a
  confirmation field that must match the selected database, or the request is rejected.
- **Remove** — a per-snapshot form with an explicit confirmation checkbox.

## Jobs

Long-running operations run in a background thread as a `BackupJob`; the job page polls
a JSON status endpoint every 2 seconds and streams the live log. Only one job runs at a
time — a second launch while a job is active is refused with a banner message.
