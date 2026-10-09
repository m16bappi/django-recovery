# django-recovery

Encrypted, deduplicated Django database and media backups, powered by [restic](https://restic.net/).

`django-recovery` turns your Django `DATABASES` (and optionally your media directory)
into restic snapshots: always encrypted, deduplicated across backups, and restorable
through a management command.

> **Status:** beta (`1.0.0b4`). Settings are the intended 1.0 API; please report issues
> before the stable release.

## Highlights

- **Encryption is always on** — every snapshot is encrypted client-side; there is no
  plaintext mode to forget to turn on.
- **Deduplication** — daily backups cost only the delta, not a full copy each time.
- **Atomic failure semantics** — a failed dump produces **no snapshot**, never a
  half-written one.
- **Uses your `STORAGES`** — point it at a Django storage alias (local disk, or S3 and
  compatibles, GCS, Azure, SFTP via django-storages); credentials live in one place.
- **Guarded restores** — typed confirmation plus a tag guard that refuses to restore
  a snapshot into the wrong database.

## Install

```bash
pip install django-recovery
```

Requires the [restic](https://restic.net/) binary (>= 0.16) on `PATH`, plus the
command-line client for each PostgreSQL or MySQL database you back up
(`pg_dump`/`psql`, `mysqldump`/`mysql`); SQLite needs nothing extra. Backups go to a
storage you already configure in `STORAGES` — Django's `FileSystemStorage` or a
[django-storages](https://django-storages.readthedocs.io/) backend your project uses.

## Quickstart

```python
# settings.py
import os

INSTALLED_APPS = [
    # ...
    "django_recovery",
]

STORAGES = {
    # ... "default" and "staticfiles" ...
    "backups": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": "/var/backups/myapp-restic"},
    },
}

RECOVERY = {
    "STORAGE": "backups",
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
    "DATABASES": ["default"],
}
```

```bash
python manage.py recovery init
python manage.py recovery backup
python manage.py recovery snapshots
```

## Documentation

Full documentation — settings reference, storage, management commands,
scheduling, and FAQ — lives at
**[m16bappi.github.io/django-recovery](https://m16bappi.github.io/django-recovery/)**.

## Related

- **[restic](https://restic.net/)** — the backup engine that does the real work.
- **[Source repository](https://github.com/m16bappi/django-recovery)** — issues and
  contributions welcome.
