"""PostgreSQL / PostGIS connector (``pg_dump`` / ``psql``)."""

from __future__ import annotations

from .base import BaseConnector


class Postgres(BaseConnector):
    """Dump/restore a PostgreSQL database via ``pg_dump`` and ``psql``.

    The password is passed out-of-band through ``PGPASSWORD`` so it never
    appears in argv.
    """

    def dump_command(self) -> list[str]:
        s = self.settings_dict
        cmd = ["pg_dump", "--clean", "--if-exists", "--no-owner"]
        if s.get("HOST"):
            cmd += ["-h", s["HOST"]]
        if s.get("PORT"):
            cmd += ["-p", str(s["PORT"])]
        if s.get("USER"):
            cmd += ["-U", s["USER"]]
        cmd += ["-d", s["NAME"]]
        return cmd

    def restore_command(self) -> list[str]:
        s = self.settings_dict
        cmd = ["psql"]
        if s.get("HOST"):
            cmd += ["-h", s["HOST"]]
        if s.get("PORT"):
            cmd += ["-p", str(s["PORT"])]
        if s.get("USER"):
            cmd += ["-U", s["USER"]]
        # The dump starts with --clean DROPs: one transaction makes a failed
        # restore roll back to the original data instead of a half-dropped DB.
        cmd += ["-d", s["NAME"], "-v", "ON_ERROR_STOP=1", "--single-transaction"]
        return cmd

    def extra_env(self) -> dict[str, str]:
        password = self.settings_dict.get("PASSWORD")
        return {"PGPASSWORD": password} if password else {}
