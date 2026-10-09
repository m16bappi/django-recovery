from django.apps import apps
from django.conf import settings


def test_app_installed():
    assert apps.is_installed("django_recovery")


def test_recovery_setting_present():
    assert settings.RECOVERY["STORAGE"] == "recovery"
    assert settings.STORAGES["recovery"]["OPTIONS"]["location"] == "/tmp/test-repo"
