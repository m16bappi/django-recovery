"""Settings parsing/validation and restic binary resolution.

``settings.RECOVERY`` follows the Django ``STORAGES`` shape: a ``BACKEND``
dotted path to a :class:`~django_recovery.backends.base.BaseBackend`
subclass plus an ``OPTIONS`` dict passed to it as keyword arguments. The
backend builds the restic repository URL and the credential environment;
operational keys (``DATABASES``, ``MEDIA``, ``TAGS``, ``BINARY``) stay
top-level.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from .backends.base import BaseBackend

_KNOWN_KEYS = {"BACKEND", "OPTIONS", "DATABASES", "MEDIA", "TAGS", "BINARY"}


@dataclass(frozen=True)
class RecoveryConfig:
    """Validated view of ``settings.RECOVERY``."""

    backend: BaseBackend
    databases: list[str]
    media: bool = False
    tags: list[str] = field(default_factory=list)
    binary: str | None = None


def get_config() -> RecoveryConfig:
    """Read and validate ``settings.RECOVERY`` into a :class:`RecoveryConfig`.

    Raises:
        ImproperlyConfigured: if ``RECOVERY`` is absent, ``BACKEND`` is
            missing, the backend class cannot be imported or is not a
            ``BaseBackend`` subclass, or the backend rejects ``OPTIONS``.
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

    backend_path = raw.get("BACKEND")
    if not backend_path:
        raise ImproperlyConfigured(
            "settings.RECOVERY['BACKEND'] is required, e.g. "
            "'django_recovery.backends.LocalBackend'."
        )

    try:
        backend_cls = import_string(backend_path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"Could not import RECOVERY['BACKEND'] {backend_path!r}: {exc}"
        ) from exc
    if not (isinstance(backend_cls, type) and issubclass(backend_cls, BaseBackend)):
        raise ImproperlyConfigured(
            f"RECOVERY['BACKEND'] {backend_path!r} is not a BaseBackend subclass."
        )

    options = raw.get("OPTIONS") or {}
    backend = backend_cls(**options)

    databases = raw.get("DATABASES") or ["default"]

    return RecoveryConfig(
        backend=backend,
        databases=list(databases),
        media=bool(raw.get("MEDIA", False)),
        tags=list(raw.get("TAGS") or []),
        binary=raw.get("BINARY"),
    )


def resolve_binary(config: RecoveryConfig) -> str:
    """Resolve the path to the restic binary.

    Resolution order:
        1. ``config.binary`` if explicitly set (returned verbatim).
        2. ``shutil.which("restic")`` on ``PATH``.
        3. Otherwise raise :class:`ImproperlyConfigured`.

    restic must be installed on the system (see the project README);
    django-recovery does not bundle a binary.
    """
    if config.binary:
        return config.binary

    found = shutil.which("restic")
    if found:
        return found

    raise ImproperlyConfigured(
        "Could not locate a restic binary. Install restic and place it on your "
        "PATH, or set RECOVERY['BINARY'] to an explicit path."
    )
