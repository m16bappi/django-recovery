"""MySQL / MariaDB connector (``mysqldump`` / ``mysql``)."""

from __future__ import annotations

from .base import BaseConnector


class MySQL(BaseConnector):
    """Dump/restore a MySQL database via ``mysqldump`` and ``mysql``.

    The password is passed out-of-band through ``MYSQL_PWD`` so it never
    appears in argv.
    """

    def dump_command(self) -> list[str]:
        s = self.settings_dict
        cmd = ["mysqldump", "--single-transaction", "--routines"]
        if s.get("HOST"):
            cmd += ["-h", s["HOST"]]
        if s.get("PORT"):
            cmd += ["-P", str(s["PORT"])]
        if s.get("USER"):
            cmd += ["-u", s["USER"]]
        cmd += [s["NAME"]]
        return cmd

    def restore_command(self) -> list[str]:
        s = self.settings_dict
        cmd = ["mysql"]
        if s.get("HOST"):
            cmd += ["-h", s["HOST"]]
        if s.get("PORT"):
            cmd += ["-P", str(s["PORT"])]
        if s.get("USER"):
            cmd += ["-u", s["USER"]]
        cmd += [s["NAME"]]
        return cmd

    def extra_env(self) -> dict[str, str]:
        password = self.settings_dict.get("PASSWORD")
        return {"MYSQL_PWD": password} if password else {}
