"""Base class for restic storage backends.

A backend turns declarative ``RECOVERY["OPTIONS"]`` into the two things the
restic subprocess needs: a repository URL string and an environment dict
carrying storage credentials. ``OPTIONS`` holds connection details only —
the repository password lives in the top-level ``RECOVERY['PASSWORD']`` /
``'PASSWORD_FILE'`` keys and is injected by the service layer, never by the
backend. Credentials are only ever placed in the subprocess environment —
never in argv and never in exception text.

The option-validation pattern mirrors django-storages' ``BaseStorage``:
``get_default_options()`` declares every accepted option with its default,
and any unknown option raises ``ImproperlyConfigured``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from django.core.exceptions import ImproperlyConfigured


class BaseBackend(ABC):
    """Base class: validates OPTIONS and builds repository URL + env."""

    def __init__(self, **options):
        defaults = self.get_default_options()
        for name, value in defaults.items():
            setattr(self, name, value)
        for name, value in options.items():
            if name not in defaults:
                raise ImproperlyConfigured(
                    f"Invalid option {name!r} for {self.__class__.__name__}. "
                    f"Valid options: {', '.join(sorted(defaults))}."
                )
            setattr(self, name, value)
        self._validate()

    @abstractmethod
    def get_default_options(self) -> dict:
        """Every accepted option with its default value.

        Only declare options the backend actually honours — ``location``
        belongs solely to the bucket/container backends that apply it.
        """

    def _validate(self) -> None:
        """Common validation; subclasses extend and call super()."""

    def _require(self, *names: str) -> None:
        """Raise unless every option in ``names`` is set and non-empty."""
        missing = [name for name in names if not getattr(self, name)]
        if missing:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} requires option(s): "
                f"{', '.join(missing)} in RECOVERY['OPTIONS']."
            )

    @property
    def repository(self) -> str:
        """The restic ``-r`` repository URL."""
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        """Storage-credential env vars for the restic subprocess.

        Passwords are not the backend's concern: the service layer adds
        ``RESTIC_PASSWORD`` / ``RESTIC_PASSWORD_FILE`` from the top-level
        ``RECOVERY`` keys.
        """
        return {}
