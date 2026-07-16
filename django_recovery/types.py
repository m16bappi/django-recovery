"""Typed shapes for ``settings.RECOVERY``.

Annotate the setting to get IDE autocomplete and static key/type checking::

    from django_recovery.types import RecoverySettings

    RECOVERY: RecoverySettings = {
        "BACKEND": "django_recovery.backends.S3Backend",
        "OPTIONS": {"bucket_name": "myapp-backups"},
        "PASSWORD": os.environ["RESTIC_PASSWORD"],
    }

These TypedDicts are also the single source of truth for runtime key
validation: :mod:`django_recovery.conf` derives its known-key sets from their
annotations, so the static and runtime views can never drift apart.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class RetentionOptions(TypedDict, total=False):
    """``RECOVERY['RETENTION']`` — restic ``forget --keep-*`` policy.

    Counts must be positive integers; ``within`` takes a restic duration
    string such as ``"7d"`` or ``"2y5m7d3h"``.
    """

    last: int
    hourly: int
    daily: int
    weekly: int
    monthly: int
    yearly: int
    within: str


class TuningOptions(TypedDict, total=False):
    """``RECOVERY['TUNING']`` — restic performance flags (1:1 mapping)."""

    compression: Literal["auto", "off", "fastest", "better", "max"]
    pack_size: int
    read_concurrency: int
    limit_upload: int
    limit_download: int
    retry_lock: str
    cache_dir: str
    no_cache: bool
    connections: int


class _RecoveryRequired(TypedDict):
    # Split base carries the only required key; RecoverySettings layers the
    # optional ones on top (typing.Required needs 3.11, this works on 3.10).
    BACKEND: str


class RecoverySettings(_RecoveryRequired, total=False):
    """The full ``settings.RECOVERY`` dict. Only ``BACKEND`` is required."""

    OPTIONS: dict[str, Any]
    PASSWORD: str
    PASSWORD_FILE: str
    DATABASES: list[str]
    MEDIA: bool
    TAGS: list[str]
    BINARY: str
    RETENTION: RetentionOptions
    TUNING: TuningOptions
    HOST: str
    SKIP_IF_UNCHANGED: bool
    MEDIA_EXCLUDE: list[str]
    EXTRA_ARGS: list[str]
