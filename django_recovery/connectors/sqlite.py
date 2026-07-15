"""SQLite connector (``sqlite3 <db> .dump`` / ``sqlite3 <db>``)."""

from __future__ import annotations

from .base import BaseConnector


class SQLite(BaseConnector):
    """Dump/restore a SQLite database file via the ``sqlite3`` CLI.

    ``.dump`` produces a consistent SQL snapshot even with open connections;
    restore reads that SQL on stdin. SQLite needs no credentials or network
    arguments, so :meth:`extra_env` is empty.
    """

    def dump_command(self) -> list[str]:
        return ["sqlite3", self.settings_dict["NAME"], ".dump"]

    def restore_command(self) -> list[str]:
        return ["sqlite3", self.settings_dict["NAME"]]

    def extra_env(self) -> dict[str, str]:
        return {}
