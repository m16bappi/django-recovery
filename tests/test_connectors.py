"""Tests for the per-engine database connectors.

These tests need no real database: they assert the exact command-line lists
and environment dicts each connector constructs from a ``DATABASES``-style
settings dict. Connectors are constructed directly where possible; the
:func:`get_connector` factory is exercised via ``override_settings``.
"""

import pytest
from django.test import override_settings

from django_recovery.connectors import MySQL, Postgres, SQLite, get_connector

# --- Postgres --------------------------------------------------------------

def test_postgres_dump_command():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.dump_command() == [
        "pg_dump", "--clean", "--if-exists", "--no-owner",
        "-h", "localhost", "-p", "5432", "-U", "app", "-d", "appdb",
    ]


def test_postgres_restore_command():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.restore_command() == [
        "psql", "-h", "localhost", "-p", "5432", "-U", "app",
        "-d", "appdb", "-v", "ON_ERROR_STOP=1",
    ]


def test_postgres_extra_env():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.extra_env() == {"PGPASSWORD": "secret"}


def test_postgres_no_password_no_env():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.extra_env() == {}


def test_postgres_omits_host_and_port_when_empty():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.dump_command() == [
        "pg_dump", "--clean", "--if-exists", "--no-owner",
        "-U", "app", "-d", "appdb",
    ]
    assert c.restore_command() == [
        "psql", "-U", "app", "-d", "appdb", "-v", "ON_ERROR_STOP=1",
    ]


# --- MySQL -----------------------------------------------------------------

def test_mysql_dump_command():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.dump_command() == [
        "mysqldump", "--single-transaction", "--routines",
        "-h", "db.internal", "-P", "3306", "-u", "app", "appdb",
    ]


def test_mysql_restore_command():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.restore_command() == [
        "mysql", "-h", "db.internal", "-P", "3306", "-u", "app", "appdb",
    ]


def test_mysql_extra_env():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.extra_env() == {"MYSQL_PWD": "secret"}


def test_mysql_no_password_no_env():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.extra_env() == {}


def test_mysql_omits_host_and_port_when_empty():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.dump_command() == [
        "mysqldump", "--single-transaction", "--routines", "-u", "app", "appdb",
    ]
    assert c.restore_command() == ["mysql", "-u", "app", "appdb"]


# --- SQLite ----------------------------------------------------------------

def test_sqlite_dump_command():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.dump_command() == ["sqlite3", "/path/db.sqlite3", ".dump"]


def test_sqlite_restore_command():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.restore_command() == ["sqlite3", "/path/db.sqlite3"]


def test_sqlite_extra_env_empty():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.extra_env() == {}


# --- stdin_filename --------------------------------------------------------

def test_stdin_filename():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.stdin_filename == "default.sql"


def test_stdin_filename_uses_alias():
    c = Postgres("analytics", {"NAME": "appdb", "USER": "", "PASSWORD": "",
                               "HOST": "", "PORT": ""})
    assert c.stdin_filename == "analytics.sql"


# --- get_connector factory -------------------------------------------------

@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
    "HOST": "localhost", "PORT": "5432",
}})
def test_get_connector_postgresql():
    c = get_connector("default")
    assert isinstance(c, Postgres)
    assert c.alias == "default"


@override_settings(DATABASES={"default": {
    "ENGINE": "django.contrib.gis.db.backends.postgis",
    "NAME": "geodb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_postgis_maps_to_postgres():
    assert isinstance(get_connector("default"), Postgres)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.mysql",
    "NAME": "appdb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_mysql():
    assert isinstance(get_connector("default"), MySQL)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.sqlite3", "NAME": "/path/db.sqlite3",
}})
def test_get_connector_sqlite():
    assert isinstance(get_connector("default"), SQLite)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.oracle",
    "NAME": "appdb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_unknown_engine_raises():
    with pytest.raises(NotImplementedError) as exc:
        get_connector("default")
    assert "django.db.backends.oracle" in str(exc.value)
