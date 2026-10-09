# Usage

## Commands

Everything is one command: `python manage.py recovery <action>`.

| Command | What it does |
|---|---|
| `recovery init` | Create the backup repository. Run once. |
| `recovery backup` | Back up all databases (and media, if `MEDIA` is on). |
| `recovery backup --database default` | Back up only this database. Repeat for more. |
| `recovery snapshots` | List all backups. |
| `recovery restore --snapshot latest --database default` | Restore the newest backup of `default`. |
| `recovery restore --snapshot 1a2b3c4d --database default` | Restore a specific backup. |
| `recovery remove 1a2b3c4d` | Delete one backup. |
| `recovery prune --dry-run` | Show which backups `RETENTION` would delete. |
| `recovery prune` | Delete backups outside `RETENTION`. |

`restore`, `remove`, and `prune` ask you to confirm first. Add `--noinput` to skip the
question in scripts.

Restore also checks that the backup belongs to the database you named, so you cannot
load the `analytics` backup into `default` by mistake.

## Run backups on a schedule

django-recovery does not run by itself. Use cron or Celery.

**cron:**

```cron
PATH=/usr/local/bin:/usr/bin:/bin

# backup every night at 02:00
0 2 * * * cd /srv/myapp && .venv/bin/python manage.py recovery backup >> /var/log/recovery.log 2>&1

# clean up old backups every Monday at 03:00
0 3 * * 1 cd /srv/myapp && .venv/bin/python manage.py recovery prune --noinput >> /var/log/recovery.log 2>&1
```

**Celery:**

```python
# myapp/tasks.py
from celery import shared_task

from django_recovery import services


@shared_task
def backup():
    return services.run_backup()   # {"default": "ok", "media": "ok"}


@shared_task
def prune():
    services.run_prune()
```

Then add both tasks to `CELERY_BEAT_SCHEDULE`.

Whichever you use, the process needs `restic` and your database tools on its `PATH`.

## Supported databases

| Database | Tools needed |
|---|---|
| PostgreSQL / PostGIS | `pg_dump`, `psql` |
| MySQL / MariaDB | `mysqldump`, `mysql` |
| SQLite | nothing |

Host, port, user, and password come from `settings.DATABASES`. You do not repeat them.

## How it works

- **Backup:** restic runs the dump command (for example `pg_dump`) and saves its output.
  If the dump fails, restic saves nothing.
- **Restore:** restic streams the backup straight into `psql` / `mysql`.
- Every backup is labelled `db:<name>` (or `media`). Labels are how `latest` and the
  restore check find the right backup.
- Dumps are not compressed first — restic compresses them after splitting them into
  chunks, so it can still skip the parts that did not change.

## FAQ

**Do I need django-storages?**
Only for cloud or SFTP storage. A local folder uses Django's own `FileSystemStorage`.

**Can I use one repository per database?**
No. All databases and media go into one repository, separated by labels.

**"repository is locked" — what now?**
A stopped backup can leave a lock. Remove it with restic, using the same repository
and password: `restic -r <repository> unlock` (for a local folder, the repository is
the folder path).

**I lost the password.**
The backups cannot be opened. There is no reset.

**Is this point-in-time recovery?**
No. A backup is the database at the moment it ran. Back up more often (deduplication
keeps it cheap) or use a WAL tool like pgBackRest for true point-in-time recovery.

**Why must restic be installed separately?**
It is a normal system program, like `pg_dump`. You update it on its own.
