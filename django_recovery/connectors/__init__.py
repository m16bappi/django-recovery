"""Per-engine database connectors and the :func:`get_connector` factory.

A connector builds the dump/restore command lines for one Django database
alias, derived from ``settings.DATABASES[alias]``. Command-line construction
ONLY — connectors never touch the backup data itself.
"""

from __future__ import annotations

from django.conf import settings

from .base import BaseConnector
from .mysql import MySQL
from .postgres import Postgres
from .sqlite import SQLite

__all__ = ["BaseConnector", "MySQL", "Postgres", "SQLite", "get_connector"]

# Map the last dotted segment of a Django ENGINE to a connector class. Both
# ``django.db.backends.postgresql`` and
# ``django.contrib.gis.db.backends.postgis`` resolve to Postgres.
_ENGINE_MAP = {
    "postgresql": Postgres,
    "postgis": Postgres,
    "mysql": MySQL,
    "sqlite3": SQLite,
}


def get_connector(alias: str) -> BaseConnector:
    """Return the connector instance for ``settings.DATABASES[alias]``.

    Raises :class:`NotImplementedError` (including the engine string) when the
    database engine has no connector.
    """
    settings_dict = settings.DATABASES[alias]
    engine = settings_dict["ENGINE"]
    connector_cls = _ENGINE_MAP.get(engine.rsplit(".", 1)[-1])
    if connector_cls is None:
        raise NotImplementedError(f"no recovery connector for engine {engine!r}")
    return connector_cls(alias, settings_dict)
