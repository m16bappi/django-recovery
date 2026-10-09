# django-recovery

!!! warning "Beta"
    `1.0.0b1` is a pre-release. Please report issues before the stable release.

Docs for other versions: use the version menu at the top of the page.

**django-recovery backs up your Django databases (and media files) with
[restic](https://restic.net/).** You run one command, and you get a backup that is:

- **encrypted** — always, before it leaves your server;
- **small** — each new backup only stores what changed;
- **safe** — if the database dump fails, no broken backup is saved;
- **easy to restore** — one command puts it back.

Backups are saved to a storage you already have in Django's `STORAGES` setting: a local
folder, or S3, Google Cloud Storage, Azure, or SFTP through
[django-storages](https://django-storages.readthedocs.io/).

## Install

```bash
pip install --pre django-recovery
```

You also need:

- **restic** 0.16 or newer, on your `PATH`
  (`apt install restic`, `brew install restic`, or `choco install restic`);
- **your database's tools**: `pg_dump` and `psql` for PostgreSQL, `mysqldump` and
  `mysql` for MySQL. SQLite needs nothing extra.

Add the app:

```python
INSTALLED_APPS = [
    # ...
    "django_recovery",
]
```

## Set up in 5 minutes

**1. Tell Django where backups go.** Add a storage for them, then point `RECOVERY` at it:

```python
# settings.py
import os

STORAGES = {
    # ... your "default" and "staticfiles" entries ...
    "backups": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": "/var/backups/myapp"},
    },
}

RECOVERY = {
    "STORAGE": "backups",
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
}
```

Want S3 instead? Change only the storage — `RECOVERY` stays the same:

```python
STORAGES = {
    # ...
    "backups": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {"bucket_name": "myapp-backups"},
    },
}
```

More examples: [Storage](storage.md).

!!! danger "Keep your password safe"
    The password encrypts your backups. If you lose it, the backups cannot be opened —
    by anyone. Store it somewhere safe, away from the backups.

**2. Create the backup repository** (once):

```bash
python manage.py recovery init
```

**3. Make a backup:**

```bash
python manage.py recovery backup
```

**4. See your backups:**

```bash
python manage.py recovery snapshots
```

```
1a2b3c4d    2026-10-09T02:00:01Z    db:default    /default.sql
```

**5. Restore when you need to:**

```bash
python manage.py recovery restore --snapshot latest --database default
```

It asks you to type the database name first, because restore replaces the current data.

**6. Run backups every night** with cron:

```cron
0 2 * * *  cd /srv/myapp && .venv/bin/python manage.py recovery backup
```

## Next

- [Storage](storage.md) — S3, Google Cloud, Azure, SFTP, local folder.
- [Settings](configuration.md) — every option, keeping old backups, speed.
- [Usage](usage.md) — all commands, Celery, supported databases, FAQ.
