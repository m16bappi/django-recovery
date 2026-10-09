"""What every database connector provides.

A connector builds the commands for its database's own tools (``pg_dump``,
``psql``, ...) and the environment variables they need, like ``PGPASSWORD``.
The data itself flows through restic, never through the connector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConnector(ABC):
    """Backup and restore commands for one database.

    restic saves the dump under :attr:`stdin_filename`, and the restore
    command reads that same file back on stdin.
    """

    def __init__(self, alias: str, settings_dict: dict):
        self.alias = alias
        self.settings_dict = settings_dict

    @abstractmethod
    def dump_command(self) -> list[str]:
        """Command that writes a backup of the database to stdout."""

    @abstractmethod
    def restore_command(self) -> list[str]:
        """Command that reads a backup from stdin and loads it into the database."""

    @abstractmethod
    def extra_env(self) -> dict[str, str]:
        """Environment variables those commands need, such as a password."""

    @property
    def stdin_filename(self) -> str:
        """The file name the backup gets inside the snapshot."""
        return f"{self.alias}.sql"
