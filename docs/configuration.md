# Settings reference

All configuration lives in a single `RECOVERY` dict in `settings.py` — the same shape as
Django's `STORAGES` setting. Nothing is configured through the UI.

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.S3Backend",   # storage backend class
    "OPTIONS": {...},                                   # kwargs for that class
    "DATABASES": ["default"],
    "MEDIA": False,
    "TAGS": [],
    "BINARY": None,
}
```

## Top-level keys

| Key         | Type        | Default       | Meaning |
|-------------|-------------|---------------|---------|
| `BACKEND`   | `str`       | *(required)*  | Dotted path to a storage backend class — see [Storage backends](backends.md). |
| `OPTIONS`   | `dict`      | `{}`          | Keyword arguments for the backend class: repository location, credentials, and the repository `password` / `password_file`. |
| `DATABASES` | `list[str]` | `["default"]` | `DATABASES` aliases to back up. Each produces one snapshot tagged `db:<alias>`. |
| `MEDIA`     | `bool`      | `False`       | When `True`, also back up `settings.MEDIA_ROOT` as a snapshot tagged `media`. |
| `TAGS`      | `list[str]` | `[]`          | Extra tags appended to every snapshot (in addition to `db:<alias>` / `media`). |
| `BINARY`    | `str`       | `None`        | Explicit path to the restic binary. Overrides `PATH` discovery. |

## Common backend options

Every backend accepts these in `OPTIONS`:

| Option          | Meaning |
|-----------------|---------|
| `password`      | Repository password as a string. Provide this **or** `password_file`. |
| `password_file` | Path to a file containing the password (mapped to restic's `RESTIC_PASSWORD_FILE`). |
| `location`      | Prefix inside the bucket/container, where the backend supports it. |

Exactly one of `password` / `password_file` is required.

## Validation

Misconfiguration fails loudly with `ImproperlyConfigured` at first use:

- unknown top-level keys in `RECOVERY` (catches old/typo'd config),
- unknown options for the chosen backend (the error lists valid options),
- missing required options (e.g. `bucket_name` for S3),
- a `BACKEND` path that doesn't import or isn't a backend class.

## Where secrets live

Credentials and the repository password are passed to the restic subprocess **via its
environment only** — never on the command line (visible in `ps`), never in logs or
exception text. Your shell environment is irrelevant: the backend builds the subprocess
environment from `OPTIONS`, and backend values override anything inherited.

Pull secrets into `OPTIONS` from wherever you keep them:

```python
"OPTIONS": {
    "secret_key": os.environ["AWS_SECRET"],          # env var
    "password_file": "/run/secrets/restic-password", # docker/k8s secret file
}
```
