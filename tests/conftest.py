"""Fixtures shared across test modules."""

import pytest

from tests.factories import recovery_settings


@pytest.fixture
def recovery(settings):
    """Set ``settings.RECOVERY`` to a minimal valid dict plus overrides.

    Uses pytest-django's ``settings`` fixture, so every change is undone
    after the test::

        def test_x(recovery):
            recovery(TAGS=["prod"])
    """

    def apply(**overrides):
        settings.RECOVERY = recovery_settings(**overrides)
        return settings.RECOVERY

    return apply
