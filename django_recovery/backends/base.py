"""Base class for restic storage backends.

A backend turns declarative ``RECOVERY["OPTIONS"]`` into the two things the
restic subprocess needs: a repository URL string and an environment dict
carrying credentials. Credentials and the repository password are only ever
placed in the subprocess environment — never in argv and never in exception
text.

The option-validation pattern mirrors django-storages' ``BaseStorage``:
``get_default_options()`` declares every accepted option with its default,
and any unknown option raises ``ImproperlyConfigured``.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured


class BaseBackend:
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

    def get_default_options(self) -> dict:
        """Every accepted option with its default value.

        Subclasses must include these common options in their own dict
        (usually via ``{**super().get_default_options(), ...}``).
        """
        return {
            "password": None,
            "password_file": None,
            "location": "",
        }

    def _validate(self) -> None:
        """Common validation; subclasses extend and call super()."""
        if bool(self.password) == bool(self.password_file):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} requires exactly one of "
                f"'password' or 'password_file' in RECOVERY['OPTIONS']."
            )

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

    def credential_env(self) -> dict[str, str]:
        """Subclass hook: credential env vars for the restic subprocess."""
        return {}

    def env(self) -> dict[str, str]:
        """Full env overlay for the restic subprocess (password + credentials)."""
        overlay = dict(self.credential_env())
        if self.password:
            overlay["RESTIC_PASSWORD"] = self.password
        else:
            overlay["RESTIC_PASSWORD_FILE"] = self.password_file
        return overlay

    def _prefixed(self, base: str) -> str:
        """Append the ``location`` prefix to ``base`` with a single slash."""
        location = (self.location or "").strip("/")
        return f"{base}/{location}" if location else base
