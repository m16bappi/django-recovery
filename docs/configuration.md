# Settings reference

All configuration lives in a single `RECOVERY` dict in `settings.py`. Where backups are
stored comes from one of your Django `STORAGES` aliases.

```python
RECOVERY = {
    "STORAGE": "backups",                               # a settings.STORAGES alias
    "PASSWORD": os.environ["RESTIC_PASSWORD"],          # repository password
    "DATABASES": ["default"],
    "MEDIA": False,
    "TAGS": [],
}
```

## Top-level keys

| Key         | Type        | Default       | Meaning |
|-------------|-------------|---------------|---------|
| `STORAGE`   | `str`       | *(required)*  | `settings.STORAGES` alias holding the repository — see [Storage](storage.md). |
| `PASSWORD`  | `str`       | `None`        | Repository password. Provide this **or** `PASSWORD_FILE`; with neither, restic reads `RESTIC_PASSWORD` from the environment. |
| `PASSWORD_FILE` | `str`   | `None`        | Path to a file containing the repository password (restic's `RESTIC_PASSWORD_FILE`). |
| `DATABASES` | `list[str]` | `["default"]` | `DATABASES` aliases to back up. Each produces one snapshot tagged `db:<alias>`. |
| `MEDIA`     | `bool`      | `False`       | When `True`, also back up `settings.MEDIA_ROOT` as a snapshot tagged `media`. |
| `TAGS`      | `list[str]` | `[]`          | Extra tags appended to every snapshot (in addition to `db:<alias>` / `media`). |
| `BINARY`    | `str`       | `None`        | Explicit path to the restic binary. Overrides `PATH` discovery. |
| `RETENTION` | `dict`      | `{}`          | Retention policy applied by [`recovery prune`](commands.md#recovery-prune) — see below. |
| `TUNING`    | `dict`      | `{}`          | Performance flags applied to every restic call — see below. |
| `HOST`      | `str`       | `None`        | Stable snapshot hostname (`--host`). **Set this in Docker/Kubernetes** — otherwise every container restart records a new hostname. |
| `SKIP_IF_UNCHANGED` | `bool` | `False`   | Skip snapshot creation when identical to the previous one (`--skip-if-unchanged`, restic ≥ 0.17). |
| `MEDIA_EXCLUDE` | `list[str]` | `[]`      | `--exclude` patterns applied to the media snapshot only (e.g. `["cache/*", "*.tmp"]`). |
| `EXTRA_ARGS` | `list[str]` | `[]`         | Escape hatch: raw arguments appended to every restic invocation. |

## Repository password

The password that encrypts the repository. Three ways to provide it, in order of
precedence:

```python
RECOVERY = {
    ...,
    "PASSWORD": os.environ["RESTIC_PASSWORD"],       # 1. inline string
    # or
    "PASSWORD_FILE": "/run/secrets/restic-password", # 2. docker/k8s secret file
    # or neither:                                    # 3. RESTIC_PASSWORD /
    #                                                #    RESTIC_PASSWORD_FILE from
    #                                                #    the process environment
}
```

Setting both `PASSWORD` and `PASSWORD_FILE` raises `ImproperlyConfigured`. The
password never goes in `STORAGES` — it encrypts the repository, it is not a storage
credential.

!!! danger "The repository password is unrecoverable"
    If you lose it, you lose the backups — restic has no reset and no backdoor.
    Store it somewhere durable and separate from the repository.

## Retention policy

```python
RECOVERY = {
    ...,
    "RETENTION": {
        "last": 5,       # always keep the 5 most recent snapshots
        "hourly": 24,    # newest snapshot per hour, for 24 hours that have one
        "daily": 7,      # newest snapshot per day, for 7 days that have one
        "weekly": 4,
        "monthly": 6,
        "yearly": 2,
        "within": "7d",  # additionally keep everything newer than 7 days
    },
}
```

Every key is optional; configure only the units you need (a common minimal policy is
`{"daily": 7, "weekly": 4, "monthly": 6}`). Counts must be positive integers; `within`
takes a restic duration string like `"7d"` or `"2y5m7d3h"`. The policy is applied by
[`recovery prune`](commands.md#recovery-prune) with `--group-by paths,tags`, so each
backup series (`db:default`, `db:analytics`, `media`) is retained **independently** —
one database's snapshots can never crowd out another's.

Advanced restic knobs not covered here (`--keep-tag`, per-unit `--keep-within-*`,
`--max-unused`) remain reachable via `EXTRA_ARGS`.

## Performance tuning

```python
RECOVERY = {
    ...,
    "TUNING": {
        "compression": "auto",   # auto | off | fastest | better | max
        "pack_size": 16,          # MiB; larger (e.g. 64) suits big repos / fast uplinks
        "read_concurrency": 2,    # parallel file reads during backup (NVMe: raise it)
        "limit_upload": 0,        # KiB/s; 0 = unlimited
        "limit_download": 0,      # KiB/s
        "retry_lock": "5m",       # wait for a locked repository instead of failing
        "cache_dir": None,        # custom restic cache location
        "no_cache": False,        # disable the local cache entirely
        "connections": None,      # concurrent backend connections (-o <backend>.connections)
    },
}
```

All optional; omitted keys use restic's defaults. These map 1:1 to restic global flags
and apply to every operation (backup, restore, prune, snapshots).

## Typing your settings

Annotate `RECOVERY` with `RecoverySettings` for IDE autocomplete and static key
checking:

```python
from django_recovery.types import RecoverySettings

RECOVERY: RecoverySettings = {
    "STORAGE": "backups",
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
}
```

## Validation

Misconfiguration fails loudly with `ImproperlyConfigured` at first use:

- unknown top-level keys in `RECOVERY` (catches old/typo'd config),
- a missing `STORAGE`, or an alias that isn't in `STORAGES` or fails to import,
- a storage class or storage setting with no restic equivalent,
- missing required values (e.g. `bucket_name` for S3).

## Where secrets live

Credentials and the repository password are passed to the restic subprocess **via its
environment only** — never on the command line (visible in `ps`), never in logs or
exception text. The subprocess environment is built from the storage's settings, and
those values override anything inherited from the shell.
Storage credentials stay where django-storages already reads them (`STORAGES` options
or `AWS_*` / `GS_*` / `AZURE_*` settings).
