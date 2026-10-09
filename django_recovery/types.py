"""Type hints for ``settings.RECOVERY``.

Annotate the setting and your editor will autocomplete keys and flag typos::

    from django_recovery.types import RecoverySettings

    RECOVERY: RecoverySettings = {
        "STORAGE": "backups",  # a settings.STORAGES alias
        "PASSWORD": os.environ["RESTIC_PASSWORD"],
    }

:mod:`django_recovery.conf` reads its list of allowed keys from these same
classes, so the hints and the runtime checks always agree.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class RetentionOptions(TypedDict, total=False):
    """``RECOVERY['RETENTION']``: which old backups ``recovery prune`` keeps.

    Counts are positive whole numbers. ``within`` is a restic duration such as
    ``"7d"`` or ``"2y5m7d3h"``.
    """

    last: int
    hourly: int
    daily: int
    weekly: int
    monthly: int
    yearly: int
    within: str


class TuningOptions(TypedDict, total=False):
    """``RECOVERY['TUNING']``: speed options, passed straight to restic.

    Except ``timeout``, which is ours: how many seconds a restic call may run
    before we stop it. Leave it unset (or 0) for no limit.
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
    # The one required key. It lives in its own base class because
    # typing.Required only arrived in Python 3.11.
    STORAGE: str


class RecoverySettings(_RecoveryRequired, total=False):
    """All of ``settings.RECOVERY``. Only ``STORAGE`` is required."""

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
