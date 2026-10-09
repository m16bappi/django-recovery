"""MySQL and MariaDB, using ``mysqldump`` and ``mysql``."""

from __future__ import annotations

from .base import BaseConnector


class MySQL(BaseConnector):
    """Back up with ``mysqldump``, restore with ``mysql``.

    The password goes in ``MYSQL_PWD``, never on the command line.
    """

    def _connection_args(self) -> list[str]:
        s = self.settings_dict
        args: list[str] = []
        host = s.get("HOST")
        if host and str(host).startswith("/"):
            # In Django, a HOST starting with "/" is a Unix socket path.
            # Sockets have no port.
            args += ["--socket", str(host)]
        else:
            if host:
                args += ["-h", host]
            if s.get("PORT"):
                args += ["-P", str(s["PORT"])]
        if s.get("USER"):
            args += ["-u", s["USER"]]
        return args

    def dump_command(self) -> list[str]:
        return [
            "mysqldump", "--single-transaction", "--routines",
            *self._connection_args(), self.settings_dict["NAME"],
        ]

    def restore_command(self) -> list[str]:
        return ["mysql", *self._connection_args(), self.settings_dict["NAME"]]

    def extra_env(self) -> dict[str, str]:
        password = self.settings_dict.get("PASSWORD")
        return {"MYSQL_PWD": password} if password else {}
