import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from django_recovery import conf
from django_recovery.backends import LocalBackend
from django_recovery.conf import RecoveryConfig, get_config, resolve_binary


def _local(**overrides):
    raw = {
        "BACKEND": "django_recovery.backends.LocalBackend",
        "OPTIONS": {"path": "/tmp/test-repo", "password": "test-password"},
    }
    raw.update(overrides)
    return raw


def test_get_config_defaults_filled():
    config = get_config()
    assert isinstance(config, RecoveryConfig)
    assert isinstance(config.backend, LocalBackend)
    assert config.backend.repository == "/tmp/test-repo"
    assert config.backend.env() == {"RESTIC_PASSWORD": "test-password"}
    assert config.databases == ["default"]
    assert config.media is False
    assert config.tags == ["test"]
    assert config.binary is None


def test_get_config_databases_defaults_when_absent():
    with override_settings(RECOVERY=_local()):
        config = get_config()
    assert config.databases == ["default"]
    assert config.media is False
    assert config.tags == []
    assert config.binary is None


def test_missing_backend_raises():
    with override_settings(RECOVERY={"OPTIONS": {"path": "/tmp/x"}}):
        with pytest.raises(ImproperlyConfigured, match="BACKEND"):
            get_config()


def test_unimportable_backend_raises():
    with override_settings(RECOVERY=_local(BACKEND="django_recovery.backends.Nope")):
        with pytest.raises(ImproperlyConfigured, match="Could not import"):
            get_config()


def test_non_backend_class_raises():
    with override_settings(RECOVERY=_local(BACKEND="django_recovery.conf.get_config")):
        with pytest.raises(ImproperlyConfigured, match="not a BaseBackend subclass"):
            get_config()


def test_unknown_top_level_key_raises():
    with override_settings(RECOVERY=_local(repository="/old/flat/style")):
        with pytest.raises(ImproperlyConfigured, match="Unknown key"):
            get_config()


def test_recovery_missing_entirely_raises():
    with override_settings(RECOVERY=None):
        with pytest.raises(ImproperlyConfigured):
            get_config()


def test_operational_keys_parsed():
    with override_settings(
        RECOVERY=_local(
            DATABASES=["default", "analytics"],
            MEDIA=True,
            TAGS=["prod"],
            BINARY="/opt/restic",
        )
    ):
        config = get_config()
    assert config.databases == ["default", "analytics"]
    assert config.media is True
    assert config.tags == ["prod"]
    assert config.binary == "/opt/restic"


def _config(binary=None):
    return RecoveryConfig(
        backend=LocalBackend(path="/repo", password="x"),
        databases=["default"],
        binary=binary,
    )


def test_resolve_binary_explicit_setting_verbatim(monkeypatch):
    # config.binary is set -> returned as-is, no lookup performed.
    def boom():  # pragma: no cover - should never be called
        raise AssertionError("should not be called")

    monkeypatch.setattr(conf.shutil, "which", lambda name: boom())
    assert resolve_binary(_config(binary="/opt/custom/restic")) == "/opt/custom/restic"


def test_resolve_binary_uses_path(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: "/usr/bin/restic")
    assert resolve_binary(_config()) == "/usr/bin/restic"


def test_resolve_binary_all_fail_raises(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: None)
    with pytest.raises(ImproperlyConfigured):
        resolve_binary(_config())
