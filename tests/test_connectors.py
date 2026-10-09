"""Tests for the per-engine database connectors.

Command-building tests need no database: they compare the exact argv and env
each connector builds from a ``DATABASES``-style dict. The SQLite scripts are
also run for real against temporary files.
"""

import subprocess
import sys

import pytest

from django_recovery.connectors import MySQL, Postgres, SQLite, get_connector
from django_recovery.connectors import sqlite as sqlite_mod
from tests.factories import create_notes_db, read_notes

PG = {"NAME": "appdb", "USER": "app", "PASSWORD": "secret",
      "HOST": "localhost", "PORT": "5432"}
MY = {"NAME": "appdb", "USER": "app", "PASSWORD": "secret",
      "HOST": "db.internal", "PORT": "3306"}
LOCAL = {"HOST": "", "PORT": "", "PASSWORD": ""}
SOCKET = {"HOST": "/var/run/mysqld/mysqld.sock"}

PG_DUMP = ["pg_dump", "--clean", "--if-exists", "--no-owner"]
PSQL_TAIL = ["-d", "appdb", "-v", "ON_ERROR_STOP=1", "--single-transaction"]
MYSQLDUMP = ["mysqldump", "--single-transaction", "--routines"]


@pytest.mark.parametrize("connector, dump, restore", [
    pytest.param(
        Postgres("default", PG),
        [*PG_DUMP, "-h", "localhost", "-p", "5432", "-U", "app", "-d", "appdb"],
        ["psql", "-h", "localhost", "-p", "5432", "-U", "app", *PSQL_TAIL],
        id="postgres",
    ),
    pytest.param(
        Postgres("default", {**PG, **LOCAL}),
        [*PG_DUMP, "-U", "app", "-d", "appdb"],
        ["psql", "-U", "app", *PSQL_TAIL],
        id="postgres-no-host-port",
    ),
    pytest.param(
        MySQL("default", MY),
        [*MYSQLDUMP, "-h", "db.internal", "-P", "3306", "-u", "app", "appdb"],
        ["mysql", "-h", "db.internal", "-P", "3306", "-u", "app", "appdb"],
        id="mysql",
    ),
    pytest.param(
        MySQL("default", {**MY, **LOCAL}),
        [*MYSQLDUMP, "-u", "app", "appdb"],
        ["mysql", "-u", "app", "appdb"],
        id="mysql-no-host-port",
    ),
    pytest.param(
        MySQL("default", {**MY, **SOCKET}),  # Django: HOST starting with "/" is a socket
        [*MYSQLDUMP, "--socket", SOCKET["HOST"], "-u", "app", "appdb"],
        ["mysql", "--socket", SOCKET["HOST"], "-u", "app", "appdb"],
        id="mysql-unix-socket",
    ),
    pytest.param(
        SQLite("default", {"NAME": "/path/db.sqlite3"}),
        [sys.executable, "-c", sqlite_mod._DUMP_SCRIPT, "/path/db.sqlite3"],
        [sys.executable, "-c", sqlite_mod._RESTORE_SCRIPT, "/path/db.sqlite3"],
        id="sqlite",
    ),
])
def test_commands(connector, dump, restore):
    assert connector.dump_command() == dump
    assert connector.restore_command() == restore


@pytest.mark.parametrize("connector, env", [
    pytest.param(Postgres("default", PG), {"PGPASSWORD": "secret"}, id="postgres"),
    pytest.param(Postgres("default", {**PG, **LOCAL}), {}, id="postgres-no-password"),
    pytest.param(
        Postgres("default", {**PG, "OPTIONS": {
            "sslmode": "verify-full", "sslrootcert": "/etc/ssl/rds.pem",
            "connect_timeout": 10, "isolation_level": 1,  # Django-only: ignored
        }}),
        {"PGSSLMODE": "verify-full", "PGSSLROOTCERT": "/etc/ssl/rds.pem",
         "PGCONNECT_TIMEOUT": "10", "PGPASSWORD": "secret"},
        id="postgres-libpq-options",
    ),
    pytest.param(MySQL("default", MY), {"MYSQL_PWD": "secret"}, id="mysql"),
    pytest.param(MySQL("default", {**MY, **LOCAL}), {}, id="mysql-no-password"),
    pytest.param(SQLite("default", {"NAME": "x"}), {}, id="sqlite"),
])
def test_extra_env(connector, env):
    assert connector.extra_env() == env


@pytest.mark.parametrize("connector, filename", [
    (Postgres("analytics", PG), "analytics.sql"),
    (SQLite("default", {"NAME": "x"}), "default.sqlite3"),  # raw file, not SQL
])
def test_stdin_filename(connector, filename):
    assert connector.stdin_filename == filename


# --- SQLite scripts, run for real ---------------------------------------------------

def test_sqlite_dump_restore_roundtrip(tmp_path):
    src = create_notes_db(tmp_path / "src.sqlite3", "hello-file")
    dumped = subprocess.run(
        SQLite("default", {"NAME": str(src)}).dump_command(),
        capture_output=True, check=True,
    ).stdout
    assert dumped.startswith(b"SQLite format 3\x00")  # raw database file, not SQL

    # Restore over an existing database with different content.
    dst = tmp_path / "dst.sqlite3"
    create_notes_db(dst, "to-be-replaced")
    subprocess.run(
        SQLite("default", {"NAME": str(dst)}).restore_command(),
        input=dumped, check=True,
    )
    assert read_notes(dst) == ["hello-file"]


def test_sqlite_dump_fails_on_missing_database(tmp_path):
    proc = subprocess.run(
        SQLite("default", {"NAME": str(tmp_path / "nope.sqlite3")}).dump_command(),
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "sqlite database not found" in proc.stderr


# --- get_connector ---------------------------------------------------------------------

@pytest.mark.parametrize("engine, connector_cls", [
    ("django.db.backends.postgresql", Postgres),
    ("django.contrib.gis.db.backends.postgis", Postgres),
    ("django.db.backends.mysql", MySQL),
    ("django.db.backends.sqlite3", SQLite),
])
def test_get_connector_picks_class_by_engine(settings, engine, connector_cls):
    settings.DATABASES = {"default": {"ENGINE": engine, **PG}}
    connector = get_connector("default")
    assert type(connector) is connector_cls
    assert connector.alias == "default"


def test_get_connector_unknown_engine_raises(settings):
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.oracle", **PG}}
    with pytest.raises(NotImplementedError, match="django.db.backends.oracle"):
        get_connector("default")


def test_get_connector_unknown_alias_lists_valid_ones():
    with pytest.raises(ValueError, match="unknown database 'typo'.*default"):
        get_connector("typo")
