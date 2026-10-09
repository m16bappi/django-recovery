"""Tests for ``settings.RECOVERY`` parsing, restic global args, and binary lookup."""

import os

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_recovery import conf
from django_recovery.conf import build_global_args, get_config, resolve_binary
from django_recovery.storage import Repository
from tests.factories import make_config

TEST_REPO = os.path.abspath("/tmp/test-repo")  # the testproject "recovery" storage


def test_testproject_settings_parse_with_defaults():
    config = get_config()
    assert config.repository == Repository(url=TEST_REPO)
    assert config.restic_env() == {"RESTIC_PASSWORD": "test-password"}
    assert (config.databases, config.media, config.tags) == (["default"], False, ["test"])
    assert config.binary is None


def test_every_option_is_parsed(recovery, settings):
    settings.MEDIA_ROOT = "/srv/media"
    recovery(
        DATABASES=("default", "analytics"),  # tuples are accepted too
        MEDIA=True,
        MEDIA_EXCLUDE=["*.tmp"],
        TAGS=["prod"],
        BINARY="/opt/restic",
        HOST="web1",
        SKIP_IF_UNCHANGED=True,
        RETENTION={"daily": 7, "within": "7d"},
        TUNING={"compression": "max", "pack_size": 64, "timeout": 3600},
        EXTRA_ARGS=["--insecure-tls"],
    )
    config = get_config()
    assert config.databases == ["default", "analytics"]
    assert (config.media, config.media_exclude, config.tags) == (True, ["*.tmp"], ["prod"])
    assert (config.binary, config.host, config.skip_if_unchanged) == (
        "/opt/restic", "web1", True,
    )
    assert config.retention == {"daily": 7, "within": "7d"}
    assert config.tuning == {"compression": "max", "pack_size": 64, "timeout": 3600}
    assert config.extra_args == ["--insecure-tls"]


@pytest.mark.parametrize("overrides, env", [
    ({"PASSWORD": "pw"}, {"RESTIC_PASSWORD": "pw"}),
    ({"PASSWORD": None, "PASSWORD_FILE": "/run/secrets/restic"},
     {"RESTIC_PASSWORD_FILE": "/run/secrets/restic"}),
    # Neither: restic reads RESTIC_PASSWORD(_FILE) from the process environment.
    ({"PASSWORD": None}, {}),
])
def test_password_sources(recovery, overrides, env):
    recovery(**overrides)
    assert get_config().restic_env() == env


LIST_KEYS = ["DATABASES", "TAGS", "MEDIA_EXCLUDE", "EXTRA_ARGS"]

INVALID = [
    pytest.param({"STORAGE": None}, "STORAGE.*required", id="storage-missing"),
    *[pytest.param({"STORAGE": v}, "STORAGE.*string", id=f"storage-{type(v).__name__}")
      for v in ({"a": 1}, 3, ["backups"])],
    pytest.param({"BACKEND": "x"}, "Unknown key.*BACKEND", id="removed-BACKEND"),
    pytest.param({"OPTIONS": {}}, "Unknown key.*OPTIONS", id="removed-OPTIONS"),
    pytest.param({"repository": "/x"}, "Unknown key", id="unknown-key"),
    pytest.param({"PASSWORD_FILE": "/f"}, "not both", id="password-and-file"),
    pytest.param({"MEDIA": True}, "MEDIA_ROOT is empty", id="media-without-root"),
    *[pytest.param({key: value}, f"{key}.*list of strings", id=f"{key}-{type(value).__name__}")
      for key in LIST_KEYS for value in ("default", ["ok", 3], {"a": 1})],
    pytest.param({"RETENTION": {"dayly": 7}}, "dayly", id="retention-unknown"),
    *[pytest.param({"RETENTION": {"daily": v}}, "positive integer", id=f"retention-{v!r}")
      for v in (0, -1, "7", True)],
    pytest.param({"RETENTION": {"within": 7}}, "duration string", id="retention-within"),
    pytest.param({"TUNING": {"speed": 11}}, "speed", id="tuning-unknown"),
    pytest.param({"TUNING": {"compression": "zstd"}}, "compression", id="tuning-compression"),
    *[pytest.param({"TUNING": {key: v}}, f"{key}.*non-negative", id=f"tuning-{key}-{v!r}")
      for key, v in (("pack_size", -1), ("timeout", -1), ("timeout", "1h"), ("timeout", True))],
]


@pytest.mark.parametrize("overrides, match", INVALID)
def test_invalid_settings_raise(recovery, overrides, match):
    recovery(**overrides)
    with pytest.raises(ImproperlyConfigured, match=match):
        get_config()


def test_missing_recovery_setting_raises(settings):
    settings.RECOVERY = None
    with pytest.raises(ImproperlyConfigured, match="RECOVERY is required"):
        get_config()


@pytest.mark.parametrize("url, tuning, extra_args, expected", [
    pytest.param("/repo", {}, [], [], id="nothing"),
    pytest.param(
        "/repo",
        {"compression": "max", "pack_size": 64, "limit_upload": 1024,
         "limit_download": 2048, "retry_lock": "5m", "cache_dir": "/c", "no_cache": True,
         "read_concurrency": 4, "timeout": 3600},  # last two are not global flags
        ["--verbose"],
        ["--compression", "max", "--pack-size", "64", "--limit-upload", "1024",
         "--limit-download", "2048", "--retry-lock", "5m", "--cache-dir", "/c",
         "--no-cache", "--verbose"],
        id="all-tuning",
    ),
    pytest.param("s3:s3.amazonaws.com/b", {"connections": 8}, [],
                 ["-o", "s3.connections=8"], id="connections-scoped-to-scheme"),
    pytest.param("C:\\backups\\repo", {"connections": 8}, [], [],
                 id="connections-skipped-for-local-path"),
])
def test_build_global_args(url, tuning, extra_args, expected):
    config = make_config(repository=Repository(url=url), tuning=tuning, extra_args=extra_args)
    assert build_global_args(config) == expected


def test_resolve_binary_prefers_explicit_setting(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: "/usr/bin/restic")
    assert resolve_binary(make_config(binary="/opt/restic")) == "/opt/restic"


def test_resolve_binary_falls_back_to_path(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: "/usr/bin/restic")
    assert resolve_binary(make_config()) == "/usr/bin/restic"


def test_resolve_binary_raises_when_not_found(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: None)
    with pytest.raises(ImproperlyConfigured, match="Could not locate a restic binary"):
        resolve_binary(make_config())


def test_known_keys_come_from_the_typeddicts():
    from django_recovery.types import RecoverySettings, RetentionOptions, TuningOptions

    assert conf._KNOWN_KEYS == frozenset(RecoverySettings.__annotations__)
    assert conf._RETENTION_KEYS == frozenset(RetentionOptions.__annotations__)
    assert conf._TUNING_KEYS == frozenset(TuningOptions.__annotations__)
    assert "STORAGE" in conf._KNOWN_KEYS  # the required key is inherited
