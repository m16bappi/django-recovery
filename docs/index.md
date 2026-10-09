# django-recovery

**Back up your Django database with one command, and restore it with another.**

```bash
python manage.py recovery backup        # save a backup
python manage.py recovery snapshots     # list your backups
python manage.py recovery restore --snapshot latest --database default   # put it back
```

Most Django projects back up with a cron job that runs `pg_dump`, gzips the output, and
copies it somewhere. That works fine until the dump fails halfway and the broken file
gets uploaded anyway. You usually find out during a restore.

django-recovery hands the job to [restic](https://restic.net/) instead. If the dump
fails, restic saves nothing. Every backup is encrypted before it leaves your server, and
each new one only stores what changed since the last, so nightly backups of a big
database stay small.

It works with PostgreSQL, MySQL, and SQLite, and it can back up your media files too.
Backups go wherever your Django `STORAGES` point: a local folder, S3, Google Cloud
Storage, Azure, or SFTP.

## Get started

**1. Install it.** It's in beta right now, so you need `--pre`:

```bash
pip install --pre django-recovery
```

You'll also need [restic](https://restic.net/) 0.16 or newer on the server, plus the dump
tools for your database: `pg_dump` and `psql` for PostgreSQL, or `mysqldump` and `mysql`
for MySQL. SQLite doesn't need anything extra.

**2. Add it to `settings.py`.** The `backups` storage here is a plain folder on the
server. The [Storage](storage.md) page shows how to use S3 or another provider instead.

```python
import os

INSTALLED_APPS = [
    # ...
    "django_recovery",
]

STORAGES = {
    # ... your existing storages ...
    "backups": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": "/var/backups/myapp"},
    },
}

RECOVERY = {
    "STORAGE": "backups",                        # where backups go
    "PASSWORD": os.environ["RESTIC_PASSWORD"],   # encrypts them
}
```

!!! danger "Keep the password somewhere safe"
    It encrypts your backups. If you lose it, nobody can open them, and there's no way
    to reset it.

**3. Create the repository and run your first backup:**

```bash
python manage.py recovery init
python manage.py recovery backup
```

You only run `init` once. After that, `recovery backup` is all you need, and the
[Usage](usage.md) page shows how to run it every night with cron or Celery.

## Where to go next

[Storage](storage.md) covers S3, Google Cloud, Azure, and SFTP. [Settings](configuration.md)
lists every option, like which databases to back up and how many old backups to keep.
[Usage](usage.md) has the full command list and a short FAQ.
