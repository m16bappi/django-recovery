# Quickstart

Five minutes from zero to a restorable, encrypted backup. This walkthrough uses a local
directory repository; swap the backend for S3/GCS/Azure later without touching anything
else — see [Storage backends](backends.md).

## 1. Configure

```python
# settings.py
import os

RECOVERY = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {
        "path": "/var/backups/myapp-restic",
        "password": os.environ["RESTIC_PASSWORD"],
    },
    "DATABASES": ["default"],   # DATABASES aliases to back up
    "MEDIA": False,             # also back up settings.MEDIA_ROOT
    "TAGS": ["prod"],           # extra tags added to every snapshot
}
```

The backend class builds everything the restic subprocess needs — repository URL and
credential environment — from `OPTIONS`. Pull secrets into `OPTIONS` however you like:
`os.environ`, `django-environ`, a secrets manager.

!!! danger "The repository password is unrecoverable"
    Losing it means losing the backups — no reset, no backdoor. Store it durably and
    separately from the repository.

## 2. Initialize the repository (once)

```bash
python manage.py recovery init
```

## 3. Back up

```bash
python manage.py recovery backup
```

## 4. Inspect

```bash
python manage.py recovery snapshots
```

```
1a2b3c4d    2026-07-15T02:00:01Z    db:default,prod    /default.sql
```

## 5. Restore (when the day comes)

```bash
python manage.py recovery restore --snapshot latest --database default
```

You'll be asked to type the database alias to confirm — restore overwrites the target
database. A tag guard also refuses to load a snapshot into a database it wasn't taken
from. Details in [Management commands](commands.md).

## 6. Schedule it

django-recovery does not run itself. Drive it from cron or Celery beat:

```cron
0 2 * * *  cd /app && python manage.py recovery backup
```

Thanks to deduplication, more frequent backups cost little extra — see
[Why django-recovery](index.md#cheaper-bandwidth-cheaper-storage).
