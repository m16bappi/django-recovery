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
| `RETENTION` | `{}` | How many old backups to keep — see below. |
| `HOST` | — | Fixed host name for backups. **Set it in Docker/Kubernetes.** |
| `SKIP_IF_UNCHANGED` | `False` | Don't save a new backup if nothing changed (restic 0.17+). |
| `BINARY` | — | Path to `restic`, if it is not on `PATH`. |
| `TUNING` | `{}` | Speed options — see below. |
| `EXTRA_ARGS` | `[]` | Extra arguments passed to every restic command. |

Typos and unknown options stop every `recovery` command with an `ImproperlyConfigured`
error, so mistakes show up before any backup runs.

## Password

Pick one:

```python
"PASSWORD": os.environ["RESTIC_PASSWORD"],         # from an environment variable
"PASSWORD_FILE": "/run/secrets/restic-password",   # from a file (Docker/Kubernetes secret)
```

Or set neither, and restic reads `RESTIC_PASSWORD` from the environment itself.

!!! danger
    Lost password = lost backups. There is no reset.

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

## Speed

All optional. They map directly to restic options:

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
}
```

## Autocomplete in your editor

```python
from django_recovery.types import RecoverySettings

RECOVERY: RecoverySettings = {"STORAGE": "backups"}
```

## Security

Passwords and keys are passed to restic through environment variables only. They never
appear on the command line, in logs, or in error messages.
