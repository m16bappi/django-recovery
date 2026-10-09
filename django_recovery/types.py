"""Typed shapes for ``settings.RECOVERY``.

Annotate the setting to get IDE autocomplete and static key/type checking::

    from django_recovery.types import RecoverySettings

    RECOVERY: RecoverySettings = {
        "STORAGE": "backups",  # a settings.STORAGES alias
        "PASSWORD": os.environ["RESTIC_PASSWORD"],
    }

These TypedDicts are also the single source of truth for runtime key
validation: :mod:`django_recovery.conf` derives its known-key sets from their
annotations, so the static and runtime views can never drift apart.
"""

from __future__ import annotations

from typing import Literal, TypedDict


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
    """``RECOVERY['TUNING']`` — restic performance flags (1:1 mapping).

    ``timeout`` is the exception: seconds before django-recovery kills a
    restic call (not a restic flag). Unset or 0 means no limit.
    """

    compression: Literal["auto", "off", "fastest", "better", "max"]
    pack_size: int
    read_concurrency: int
    limit_upload: int
    limit_download: int
    retry_lock: str
    cache_dir: str
    no_cache: bool
    connections: int
    timeout: int


class _RecoveryRequired(TypedDict):
    # Split base carries the only required key; RecoverySettings layers the
    # optional ones on top (typing.Required needs 3.11, this works on 3.10).
    STORAGE: str


class RecoverySettings(_RecoveryRequired, total=False):
    """The full ``settings.RECOVERY`` dict. Only ``STORAGE`` is required."""

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
