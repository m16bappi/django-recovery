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

Restore also checks that the backup belongs to the database you named, so you can't
load the `analytics` backup into `default` by mistake.

## Run backups on a schedule

django-recovery doesn't schedule anything itself. Use whatever you already have, like
cron or Celery.

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

Host, port, user, and password come from `settings.DATABASES`, so you don't repeat them
anywhere.

## How it works

When you back up, restic runs the dump command itself (for example `pg_dump`) and saves
what it prints. If the dump fails, restic saves nothing, so you never end up with a
half-written backup. Restoring works the other way around: restic streams the backup
straight into `psql` or `mysql`.

Every backup gets a label, `db:<name>` or `media`. That's how `latest` finds the newest
backup for a database, and how restore knows it has the right one.

The dumps aren't compressed before restic sees them. restic splits them into chunks
first and compresses after that, which is what lets it skip the parts that didn't
change since the last backup.

## FAQ

**Do I need django-storages?**
Only for cloud or SFTP storage. A local folder uses Django's own `FileSystemStorage`.

**Can I use one repository per database?**
No. All databases and media go into one repository, separated by labels.

**What do I do about "repository is locked"?**
A backup that got killed halfway can leave a lock behind. Remove it with restic, using
the same repository and password: `restic -r <repository> unlock`. For a local folder,
the repository is just the folder path.

**I lost the password. Can I get my backups back?**
No. Without the password the backups can't be opened, and there's no reset.

**Is this point-in-time recovery?**
No. A backup is the database at the moment it ran. Back up more often (deduplication
keeps it cheap) or use a WAL tool like pgBackRest for true point-in-time recovery.

**Why do I have to install restic separately?**
It's a normal system program, like `pg_dump`, so you can update it on its own schedule.
