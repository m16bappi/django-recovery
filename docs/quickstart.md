# Quickstart

Five minutes from zero to a restorable, encrypted backup. This walkthrough uses a local
directory repository; point it at an S3/GCS/Azure/SFTP storage later without touching
anything else — see [Storage](storage.md).

## 1. Configure

```python
# settings.py
import os

STORAGES = {
    # ... your existing "default" and "staticfiles" entries ...
    "backups": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": "/var/backups/myapp-restic"},
    },
}

RECOVERY = {
    "STORAGE": "backups",       # the STORAGES alias holding the repository
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
    "DATABASES": ["default"],   # DATABASES aliases to back up
    "MEDIA": False,             # also back up settings.MEDIA_ROOT
    "TAGS": ["prod"],           # extra tags added to every snapshot
}
```

django-recovery reads the repository location (and, for cloud storages, the
credentials) from that `STORAGES` alias. Moving to S3 later means pointing the alias at
a django-storages backend — `RECOVERY` stays the same. Keep the directory outside
`MEDIA_ROOT`; django-recovery refuses a repository inside it.

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
