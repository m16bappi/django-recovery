"""Reads and checks ``settings.RECOVERY``, and finds the restic binary.

Where backups go comes from the ``STORAGES`` alias in ``RECOVERY['STORAGE']``
(see :mod:`django_recovery.storage`). Everything else in ``RECOVERY`` (which
databases, media, tags, retention, speed options) is read here.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .storage import Repository, repository_from_storage
from .types import RecoverySettings, RetentionOptions, TuningOptions

# The allowed keys come straight from the TypedDicts in .types, so the type
# hints users see and the checks below can't get out of sync.
_KNOWN_KEYS = frozenset(RecoverySettings.__annotations__)
_RETENTION_KEYS = frozenset(RetentionOptions.__annotations__)
_TUNING_KEYS = frozenset(TuningOptions.__annotations__)

_COMPRESSION_MODES = {"auto", "off", "fastest", "better", "max"}


@dataclass(frozen=True)
class RecoveryConfig:
    """``settings.RECOVERY`` after it has been checked."""

    repository: Repository
    databases: list[str]
    media: bool = False
    tags: list[str] = field(default_factory=list)
    binary: str | None = None
    password: str | None = None
    password_file: str | None = None
    retention: dict = field(default_factory=dict)
    tuning: dict = field(default_factory=dict)
    host: str | None = None
    skip_if_unchanged: bool = False
    media_exclude: list[str] = field(default_factory=list)
    extra_args: list[str] = field(default_factory=list)

    def restic_env(self) -> dict[str, str]:
        """Environment variables for restic: storage credentials plus the password.

        If neither ``PASSWORD`` nor ``PASSWORD_FILE`` is set, no password is
        added and restic falls back to ``RESTIC_PASSWORD`` /
        ``RESTIC_PASSWORD_FILE`` from the environment.
        """
        env = dict(self.repository.env)
        if self.password:
            env["RESTIC_PASSWORD"] = self.password
        elif self.password_file:
            env["RESTIC_PASSWORD_FILE"] = str(self.password_file)
        return env


def _validate_retention(raw: dict) -> dict:
    unknown = set(raw) - _RETENTION_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in RECOVERY['RETENTION']: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_RETENTION_KEYS))}."
        )
    for key, value in raw.items():
        if key == "within":
            if not isinstance(value, str) or not value:
                raise ImproperlyConfigured(
                    "RECOVERY['RETENTION']['within'] must be a non-empty restic "
                    "duration string, e.g. '7d' or '2y5m7d3h'."
                )
        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ImproperlyConfigured(
                f"RECOVERY['RETENTION'][{key!r}] must be a positive integer."
            )
    return dict(raw)


def _validate_tuning(raw: dict) -> dict:
    unknown = set(raw) - _TUNING_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in RECOVERY['TUNING']: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_TUNING_KEYS))}."
        )
    compression = raw.get("compression")
    if compression is not None and compression not in _COMPRESSION_MODES:
        raise ImproperlyConfigured(
            f"RECOVERY['TUNING']['compression'] must be one of "
            f"{', '.join(sorted(_COMPRESSION_MODES))}; got {compression!r}."
        )
    for key in ("pack_size", "read_concurrency", "limit_upload", "limit_download",
                "connections", "timeout"):
        value = raw.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ImproperlyConfigured(
                f"RECOVERY['TUNING'][{key!r}] must be a non-negative integer."
            )
    return dict(raw)


def _str_list(raw: dict, key: str) -> list[str]:
    """``RECOVERY[key]`` as a list of strings, or ``[]`` if it isn't set.

    A plain string is an error. Otherwise ``"default"`` would quietly turn into
    ``['d', 'e', 'f', ...]``.
    """
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ImproperlyConfigured(
            f"RECOVERY[{key!r}] must be a list of strings, e.g. [\"value\"]; "
            f"got {value!r}."
        )
    return list(value)


def _build_repository(raw: dict) -> Repository:
    """Look up the ``STORAGES`` alias named in ``STORAGE`` and turn it into a repository."""
    from django.core.files.storage import InvalidStorageError, storages

    alias = raw.get("STORAGE")
    if not alias or not isinstance(alias, str):
        raise ImproperlyConfigured(
            "settings.RECOVERY['STORAGE'] is required: the settings.STORAGES "
            f"alias (a string) to keep backups in, e.g. 'backups'; got {alias!r}."
        )
    try:
        storage = storages[alias]
    except InvalidStorageError as exc:
        # Unknown alias, or a storage class that can't be imported (for
        # example django-storages or boto3 isn't installed).
        raise ImproperlyConfigured(
            f"RECOVERY['STORAGE'] {alias!r} could not be loaded: {exc}"
        ) from exc
    return repository_from_storage(storage)


def get_config() -> RecoveryConfig:
    """Read ``settings.RECOVERY``, check it, and return a :class:`RecoveryConfig`.

    Any problem raises ``ImproperlyConfigured`` with a message that says what
    to fix, before a single restic command runs.
    """
    raw = getattr(settings, "RECOVERY", None)
    if not raw:
        raise ImproperlyConfigured(
            "settings.RECOVERY is required to use django-recovery."
        )

    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in settings.RECOVERY: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_KNOWN_KEYS))}."
        )

    repository = _build_repository(raw)

    if raw.get("MEDIA") and not settings.MEDIA_ROOT:
        raise ImproperlyConfigured(
            "RECOVERY['MEDIA'] is on but settings.MEDIA_ROOT is empty; set "
            "MEDIA_ROOT or turn MEDIA off."
        )

    if raw.get("PASSWORD") and raw.get("PASSWORD_FILE"):
        raise ImproperlyConfigured(
            "settings.RECOVERY accepts only one of 'PASSWORD' or "
            "'PASSWORD_FILE', not both."
        )

    return RecoveryConfig(
        repository=repository,
        databases=_str_list(raw, "DATABASES") or ["default"],
        media=bool(raw.get("MEDIA", False)),
        tags=_str_list(raw, "TAGS"),
        binary=raw.get("BINARY"),
        password=raw.get("PASSWORD"),
        password_file=raw.get("PASSWORD_FILE"),
        retention=_validate_retention(raw.get("RETENTION") or {}),
        tuning=_validate_tuning(raw.get("TUNING") or {}),
        host=raw.get("HOST"),
        skip_if_unchanged=bool(raw.get("SKIP_IF_UNCHANGED", False)),
        media_exclude=_str_list(raw, "MEDIA_EXCLUDE"),
        extra_args=_str_list(raw, "EXTRA_ARGS"),
    )


# The repository kinds that understand restic's -o <kind>.connections option.
# Local folders have no "kind:" prefix and ignore it anyway.
_REPO_SCHEMES = {"s3", "gs", "azure", "sftp"}


def build_global_args(config: RecoveryConfig) -> list[str]:
    """Turn ``TUNING`` and ``EXTRA_ARGS`` into flags added to every restic command.

    ``read_concurrency`` and ``timeout`` are handled elsewhere: the first only
    applies to ``backup``, the second isn't a restic flag at all.
    """
    tuning = config.tuning
    args: list[str] = []
    if tuning.get("compression"):
        args += ["--compression", tuning["compression"]]
    if tuning.get("pack_size"):
        args += ["--pack-size", str(tuning["pack_size"])]
    if tuning.get("limit_upload"):
        args += ["--limit-upload", str(tuning["limit_upload"])]
    if tuning.get("limit_download"):
        args += ["--limit-download", str(tuning["limit_download"])]
    if tuning.get("retry_lock"):
        args += ["--retry-lock", str(tuning["retry_lock"])]
    if tuning.get("cache_dir"):
        args += ["--cache-dir", str(tuning["cache_dir"])]
    if tuning.get("no_cache"):
        args += ["--no-cache"]
    if tuning.get("connections"):
        scheme = config.repository.url.split(":", 1)[0]
        if scheme in _REPO_SCHEMES:
            args += ["-o", f"{scheme}.connections={tuning['connections']}"]
    args += config.extra_args
    return args


def resolve_binary(config: RecoveryConfig) -> str:
    """Path to restic: ``RECOVERY['BINARY']`` if set, otherwise the one on ``PATH``."""
    if config.binary:
        return config.binary

    if binary := shutil.which("restic"):
        return binary

    raise ImproperlyConfigured(
        "Could not locate a restic binary. Install restic and place it on your "
        "PATH, or set RECOVERY['BINARY'] to an explicit path."
    )
