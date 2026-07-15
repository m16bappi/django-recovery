"""Base class for per-engine database connectors.

A connector never transforms backup data; it only *constructs* the argv lists
for the external dump/restore client (``pg_dump``/``psql`` etc.) from a Django
``DATABASES[alias]`` settings dict, plus any extra environment variables that
client needs (e.g. ``PGPASSWORD``). The dump/restore streams themselves flow
through restic's stdin/stdout — connectors only build commands.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConnector(ABC):
    """Builds dump/restore commands for one database alias.

    Subclasses implement :meth:`dump_command`, :meth:`restore_command` and
    :meth:`extra_env` for their engine. The dump is written to restic under
    :attr:`stdin_filename` and the restore reads that same file on stdin.
    """

    def __init__(self, alias: str, settings_dict: dict):
        self.alias = alias
        self.settings_dict = settings_dict

    @abstractmethod
    def dump_command(self) -> list[str]:
        """Argv that writes a SQL dump of this database to stdout."""

    @abstractmethod
    def restore_command(self) -> list[str]:
        """Argv that loads a SQL dump into this database from stdin."""

    @abstractmethod
    def extra_env(self) -> dict[str, str]:
        """Extra environment variables the dump/restore client needs."""

    @property
    def stdin_filename(self) -> str:
        """Logical filename restic records for this database's dump stream."""
        return f"{self.alias}.sql"
