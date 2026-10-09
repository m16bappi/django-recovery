"""SQLite, backed up as the database file itself.

The snapshot holds a copy of the whole file (``<alias>.sqlite3``), not SQL
text. Both directions run a short Python script with the same interpreter as
Django, using SQLite's own backup API. That gives a consistent copy even while
the site is running, and you don't need the ``sqlite3`` command-line tool.
"""

from __future__ import annotations

import sys

from .base import BaseConnector

# Copy the live database into a temp file, then print its bytes for restic.
# A missing database file is an error: connecting would silently create an
# empty one, and we'd "successfully" back up nothing.
_DUMP_SCRIPT = """\
import os, shutil, sqlite3, sys, tempfile
db = sys.argv[1]
if not os.path.exists(db):
    sys.exit("sqlite database not found: " + db)
fd, tmp = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
try:
    src = sqlite3.connect(db)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as fh:
        shutil.copyfileobj(fh, sys.stdout.buffer)
finally:
    os.remove(tmp)
"""

# The reverse: save restic's bytes to a temp file, then copy that over the
# live database (creating it if it doesn't exist).
_RESTORE_SCRIPT = """\
import os, shutil, sqlite3, sys, tempfile
fd, tmp = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
try:
    with open(tmp, "wb") as fh:
        shutil.copyfileobj(sys.stdin.buffer, fh)
    src = sqlite3.connect(tmp)
    dst = sqlite3.connect(sys.argv[1])
    src.backup(dst)
    dst.close()
    src.close()
finally:
    os.remove(tmp)
"""


class SQLite(BaseConnector):
    """Back up and restore a SQLite database file. No credentials needed."""

    def dump_command(self) -> list[str]:
        return [sys.executable, "-c", _DUMP_SCRIPT, str(self.settings_dict["NAME"])]

    def restore_command(self) -> list[str]:
        return [sys.executable, "-c", _RESTORE_SCRIPT, str(self.settings_dict["NAME"])]

    def extra_env(self) -> dict[str, str]:
        return {}

    @property
    def stdin_filename(self) -> str:
        """``<alias>.sqlite3``, because the snapshot holds the database file itself."""
        return f"{self.alias}.sqlite3"
