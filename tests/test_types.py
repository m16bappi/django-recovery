"""The TypedDicts in django_recovery.types drive runtime key validation."""

from django_recovery import conf
from django_recovery.types import RecoverySettings, RetentionOptions, TuningOptions


def test_known_keys_derive_from_recovery_settings():
    assert conf._KNOWN_KEYS == frozenset(RecoverySettings.__annotations__)
    # Required key present alongside the optional ones (inherited annotations).
    assert "BACKEND" in conf._KNOWN_KEYS
    assert "PASSWORD" in conf._KNOWN_KEYS
    assert "TUNING" in conf._KNOWN_KEYS


def test_retention_and_tuning_keys_derive_from_typeddicts():
    assert conf._RETENTION_KEYS == frozenset(RetentionOptions.__annotations__)
    assert conf._TUNING_KEYS == frozenset(TuningOptions.__annotations__)
    assert "within" in conf._RETENTION_KEYS
    assert "compression" in conf._TUNING_KEYS


def test_recovery_settings_annotation_accepts_valid_dict():
    # Static-typing helper is usable at runtime as a plain dict.
    settings: RecoverySettings = {
        "BACKEND": "django_recovery.backends.LocalBackend",
        "OPTIONS": {"path": "/repo"},
        "PASSWORD": "pw",
        "RETENTION": {"daily": 7},
        "TUNING": {"compression": "max"},
    }
    assert settings["BACKEND"].endswith("LocalBackend")
