"""One connector per database engine, and :func:`get_connector` to pick the right one.

A connector knows which commands back up and restore a database, built from
its ``settings.DATABASES`` entry. It never touches the data itself.
"""

from __future__ import annotations

from django.conf import settings

from .base import BaseConnector
from .mysql import MySQL
from .postgres import Postgres
from .sqlite import SQLite

__all__ = ["BaseConnector", "MySQL", "Postgres", "SQLite", "get_connector"]

# Keyed by the last part of Django's ENGINE string, so both
# "django.db.backends.postgresql" and PostGIS map to Postgres.
_ENGINE_MAP = {
    "postgresql": Postgres,
    "postgis": Postgres,
    "mysql": MySQL,
    "sqlite3": SQLite,
}


def get_connector(alias: str) -> BaseConnector:
    """The connector for ``settings.DATABASES[alias]``.

    Raises ``ValueError`` for an alias that isn't in ``DATABASES`` (a typo in
    ``--database``, say) and ``NotImplementedError`` for an engine we don't
    support.
    """
    if alias not in settings.DATABASES:
        raise ValueError(
            f"unknown database {alias!r}; settings.DATABASES has: "
            f"{', '.join(sorted(settings.DATABASES))}"
        )
    settings_dict = settings.DATABASES[alias]
    engine = settings_dict["ENGINE"]
    connector_cls = _ENGINE_MAP.get(engine.rsplit(".", 1)[-1])
    if connector_cls is None:
        raise NotImplementedError(f"no recovery connector for engine {engine!r}")
    return connector_cls(alias, settings_dict)
