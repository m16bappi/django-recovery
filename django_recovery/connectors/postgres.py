"""PostgreSQL and PostGIS, using ``pg_dump`` and ``psql``."""

from __future__ import annotations

from .base import BaseConnector

# Connection OPTIONS that pg_dump and psql understand, and the environment
# variable each one reads. Django-only options (isolation_level, pool, ...)
# mean nothing to the command-line tools, so they're left out.
_LIBPQ_ENV = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslcrl": "PGSSLCRL",
    "service": "PGSERVICE",
    "passfile": "PGPASSFILE",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "options": "PGOPTIONS",
}


class Postgres(BaseConnector):
    """Back up with ``pg_dump``, restore with ``psql``.

    The password goes in ``PGPASSWORD``, never on the command line.
    """

    def _connection_args(self) -> list[str]:
        s = self.settings_dict
        args: list[str] = []
        if s.get("HOST"):
            args += ["-h", s["HOST"]]
        if s.get("PORT"):
            args += ["-p", str(s["PORT"])]
        if s.get("USER"):
            args += ["-U", s["USER"]]
        return args

    def dump_command(self) -> list[str]:
        return [
            "pg_dump", "--clean", "--if-exists", "--no-owner",
            *self._connection_args(), "-d", self.settings_dict["NAME"],
        ]

    def restore_command(self) -> list[str]:
        # The dump starts by dropping tables. Running it as one transaction
        # means a failed restore rolls back to the original data instead of
        # leaving a half-empty database.
        return [
            "psql", *self._connection_args(), "-d", self.settings_dict["NAME"],
            "-v", "ON_ERROR_STOP=1", "--single-transaction",
        ]

    def extra_env(self) -> dict[str, str]:
        """``PGPASSWORD`` plus SSL and other connection ``OPTIONS``.

        Without these, a database that requires ``sslmode='verify-full'``
        would be dumped over whatever connection libpq picks by default.
        """
        options = self.settings_dict.get("OPTIONS") or {}
        env = {
            var: str(options[key]) for key, var in _LIBPQ_ENV.items()
            if options.get(key) is not None
        }
        password = self.settings_dict.get("PASSWORD")
        if password:
            env["PGPASSWORD"] = password
        return env
