from django.apps import apps
from django.conf import settings


def test_app_installed():
    assert apps.is_installed("django_recovery")


def test_recovery_setting_present():
    assert settings.RECOVERY["BACKEND"] == "django_recovery.backends.LocalBackend"
    assert settings.RECOVERY["OPTIONS"]["path"] == "/tmp/test-repo"
