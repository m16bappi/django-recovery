"""Tests for the ``recovery`` management command.

The command is a thin argparse layer over :mod:`django_recovery.services`, so
each service function is replaced with a mock and confirmation prompts are
answered through ``builtins.input``. Nothing touches restic or a database.

``call_command`` takes the subcommand as the first positional argument;
subparser options are passed as keyword arguments, e.g.
``call_command("recovery", "restore", snapshot="latest", database="default")``.
"""

from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from django_recovery import services
from django_recovery.restic import ResticError
from tests.factories import make_snapshot


@pytest.fixture
def patch_service(monkeypatch):
    """Replace ``services.<name>`` with a mock and return it."""

    def patch(name, **mock_kwargs):
        mock = MagicMock(**mock_kwargs)
        monkeypatch.setattr(services, name, mock)
        return mock

    return patch


@pytest.fixture
def answer(monkeypatch):
    """Answer every confirmation prompt with ``text``."""
    return lambda text: monkeypatch.setattr("builtins.input", lambda prompt="": text)


@pytest.fixture
def no_prompt(monkeypatch):
    def fail(prompt=""):  # pragma: no cover - only runs if the test fails
        raise AssertionError(f"unexpected prompt: {prompt!r}")

    monkeypatch.setattr("builtins.input", fail)


@pytest.fixture(autouse=True)
def retention(recovery):
    """A RETENTION policy, so ``prune`` is runnable in every test."""
    recovery(RETENTION={"daily": 7})


# (subcommand args, call_command kwargs, service function, answer that confirms)
DESTRUCTIVE = [
    pytest.param(("restore",), {"snapshot": "latest", "database": "default"},
                 "run_restore", "default", id="restore"),
    pytest.param(("remove", "abc123"), {}, "remove_snapshot", "yes", id="remove"),
    pytest.param(("prune",), {}, "run_prune", "yes", id="prune"),
]


# --- simple pass-through ------------------------------------------------------

def test_init_calls_service(patch_service):
    run_init = patch_service("run_init")
    call_command("recovery", "init")
    run_init.assert_called_once()


def test_backup_passes_databases_and_prints_summary(patch_service, capsys):
    run_backup = patch_service("run_backup", return_value={"default": "ok"})

    call_command("recovery", "backup", database=["default"])

    assert run_backup.call_args.kwargs["databases"] == ["default"]
    assert "default: ok" in capsys.readouterr().out


@pytest.mark.parametrize("snapshots, expected", [
    ([make_snapshot("abc123def456", tags=("db:default", "test"))],
     "abc123de\t2026-07-14T10:00:00Z\tdb:default,test"),
    ([], "No snapshots."),
])
def test_snapshots_output(patch_service, capsys, snapshots, expected):
    patch_service("list_snapshots", return_value=snapshots)
    call_command("recovery", "snapshots")
    assert expected in capsys.readouterr().out


# --- confirmations -------------------------------------------------------------------

@pytest.mark.parametrize("args, kwargs, service, confirm", DESTRUCTIVE)
def test_destructive_command_runs_when_confirmed(
    patch_service, answer, args, kwargs, service, confirm
):
    mock = patch_service(service)
    answer(confirm)
    call_command("recovery", *args, **kwargs)
    mock.assert_called_once()


@pytest.mark.parametrize("args, kwargs, service, confirm", DESTRUCTIVE)
def test_destructive_command_aborts_on_wrong_answer(
    patch_service, answer, args, kwargs, service, confirm
):
    mock = patch_service(service)
    answer("nope")
    with pytest.raises(CommandError, match="aborted"):
        call_command("recovery", *args, **kwargs)
    mock.assert_not_called()


@pytest.mark.usefixtures("no_prompt")
@pytest.mark.parametrize("args, kwargs, service, confirm", DESTRUCTIVE)
def test_noinput_skips_the_prompt(patch_service, args, kwargs, service, confirm):
    mock = patch_service(service)
    call_command("recovery", *args, noinput=True, **kwargs)
    mock.assert_called_once()


def test_restore_passes_alias_and_snapshot(patch_service):
    run_restore = patch_service("run_restore")
    call_command("recovery", "restore", snapshot="latest", database="default", noinput=True)
    kwargs = run_restore.call_args.kwargs
    assert (kwargs["alias"], kwargs["snapshot_id"]) == ("default", "latest")


@pytest.mark.usefixtures("no_prompt")
def test_prune_dry_run_never_prompts(patch_service):
    run_prune = patch_service("run_prune")
    call_command("recovery", "prune", dry_run=True)
    assert run_prune.call_args.kwargs["dry_run"] is True


def test_prune_without_retention_refuses(patch_service, recovery):
    recovery()  # no RETENTION
    run_prune = patch_service("run_prune")
    with pytest.raises(CommandError, match="RETENTION"):
        call_command("recovery", "prune", noinput=True)
    run_prune.assert_not_called()


# --- error reporting ----------------------------------------------------------------------

@pytest.mark.parametrize("exc", [
    ResticError(1, "Fatal: unable to open config file"),
    FileNotFoundError(2, "No such file or directory", "psql"),
    ImproperlyConfigured("settings.RECOVERY['STORAGE'] is required"),
    ValueError("snapshot nope not found"),
])
def test_expected_errors_become_command_error(patch_service, exc):
    patch_service("run_backup", side_effect=exc)
    with pytest.raises(CommandError) as info:
        call_command("recovery", "backup")
    assert str(info.value) == str(exc)
    assert info.value.__cause__ is exc


def test_unexpected_errors_keep_their_traceback(patch_service):
    patch_service("run_backup", side_effect=TypeError("bug"))
    with pytest.raises(TypeError):
        call_command("recovery", "backup")
