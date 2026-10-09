# Settings

Everything goes in one `RECOVERY` dict in `settings.py`. Only `STORAGE` is required.

```python
RECOVERY = {
    "STORAGE": "backups",                        # which STORAGES entry holds backups
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
    "DATABASES": ["default"],                    # which databases to back up
    "MEDIA": True,                               # also back up MEDIA_ROOT
    "RETENTION": {"daily": 7, "weekly": 4, "monthly": 6},
}
```

## All options

| Option | Default | What it does |
|---|---|---|
| `STORAGE` | *required* | Name of the `STORAGES` entry to save backups in. See [Storage](storage.md). |
| `PASSWORD` | — | Password that encrypts the backups. |
| `PASSWORD_FILE` | — | Path to a file holding the password (use this **or** `PASSWORD`). |
| `DATABASES` | `["default"]` | Database names (from `settings.DATABASES`) to back up. |
| `MEDIA` | `False` | Also back up the `MEDIA_ROOT` folder. |
| `MEDIA_EXCLUDE` | `[]` | Media files to skip, e.g. `["cache/*", "*.tmp"]`. |
| `TAGS` | `[]` | Extra labels added to every backup. |
| `RETENTION` | `{}` | How many old backups to keep (see below). |
| `HOST` | — | Fixed host name for backups. **Set it in Docker/Kubernetes.** |
| `SKIP_IF_UNCHANGED` | `False` | Don't save a new backup if nothing changed (restic 0.17+). |
| `BINARY` | — | Path to `restic`, if it is not on `PATH`. |
| `TUNING` | `{}` | Speed options (see below). |
| `EXTRA_ARGS` | `[]` | Extra arguments passed to every restic command. |

If you misspell an option, every `recovery` command stops with an `ImproperlyConfigured`
error. Better to find out now than when a backup quietly does the wrong thing.

## Password

Pick one:

```python
"PASSWORD": os.environ["RESTIC_PASSWORD"],         # from an environment variable
"PASSWORD_FILE": "/run/secrets/restic-password",   # from a file (Docker/Kubernetes secret)
```

Or set neither, and restic reads `RESTIC_PASSWORD` from the environment itself.

!!! danger
    If you lose the password, the backups are gone for good. There's no reset.

## Keeping old backups

`RETENTION` decides which backups `recovery prune` keeps:

```python
"RETENTION": {
    "daily": 7,     # one backup for each of the last 7 days
    "weekly": 4,    # one for each of the last 4 weeks
    "monthly": 6,   # one for each of the last 6 months
}
```

Other keys: `last` (the newest N), `hourly`, `yearly`, and `within` (keep everything
newer than, for example, `"7d"`). Each database and the media files are counted
separately, so one never pushes out another.

One catch: your `TAGS` are part of that grouping too. If you change `TAGS` later, new
backups start a fresh group, and the old ones are no longer counted against the new
policy. Clean those up once with `restic forget` (or `recovery remove`).

## Speed

You can skip this section. The defaults are fine for most projects, but if backups are
slow or use too much bandwidth, these map straight to restic's own options:

```python
"TUNING": {
    "compression": "auto",   # auto, off, fastest, better, max
    "pack_size": 16,         # MiB; try 64 for big databases
    "read_concurrency": 2,   # parallel reads during backup
    "limit_upload": 0,       # KiB/s, 0 = no limit
    "limit_download": 0,     # KiB/s
    "retry_lock": "5m",      # wait if another backup is running
    "connections": 5,        # parallel connections to cloud storage
    "cache_dir": None,       # where restic keeps its cache
    "no_cache": False,       # turn the cache off
    "timeout": 3600,         # seconds before a stuck restic call is stopped
}
```

`timeout` is the only one that isn't a restic option. Without it, a repository that stops
responding can keep a cron job or Celery worker waiting forever. If it does trigger, run
`restic unlock` before the next backup.

## Autocomplete in your editor

```python
from django_recovery.types import RecoverySettings

RECOVERY: RecoverySettings = {"STORAGE": "backups"}
```

## Security

Passwords and keys are passed to restic through environment variables only. They never
appear on the command line, in logs, or in error messages.

restic runs the database dump itself, so `pg_dump` and `mysqldump` start with the same
environment as restic: your storage keys and the repository password included. That's
fine for the standard tools, but keep it in mind if you swap in a custom dump script.
