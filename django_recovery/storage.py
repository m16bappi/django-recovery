"""Derive the restic repository from a configured Django ``Storage``.

``RECOVERY['STORAGE']`` names a ``settings.STORAGES`` alias. The storage
instance Django resolves for it already merges that alias' ``OPTIONS`` with
the global ``AWS_*`` / ``GS_*`` / ``AZURE_*`` / ``SFTP_*`` settings (or, for
Django's own ``FileSystemStorage``, ``MEDIA_ROOT``), so its attributes are the
effective connection details. This module only *reads* them and builds the
restic repository URL plus the credential environment; restic still performs
all I/O.

Storage classes are matched by dotted path along the instance's MRO, so
``storages`` is never imported here and user subclasses (``class
MediaStorage(S3Storage)``) and the ``S3Boto3Storage`` alias match too.
Settings with no restic equivalent raise ``ImproperlyConfigured`` rather than
being silently dropped — a backup silently going somewhere else, or with a
different identity, is worse than a clear error.

Credentials are only ever placed in the returned env — never in the URL
(which lands in argv) and never in exception text.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_DEFAULT_S3_ENDPOINT = "s3.amazonaws.com"
_DEFAULT_AZURE_SUFFIX = "core.windows.net"


@dataclass(frozen=True)
class Repository:
    """A restic ``-r`` repository URL plus the env vars needed to reach it."""

    url: str
    env: dict[str, str] = field(default_factory=dict)


def _name(storage) -> str:
    return type(storage).__name__


def _unsupported(storage, setting: str, hint: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(
        f"{_name(storage)} setting {setting!r} has no restic equivalent and "
        f"cannot be used with RECOVERY['STORAGE']. {hint}"
    )


def _require(storage, *names: str) -> None:
    missing = [name for name in names if not getattr(storage, name, None)]
    if missing:
        raise ImproperlyConfigured(
            f"{_name(storage)} used by RECOVERY['STORAGE'] requires setting(s): "
            f"{', '.join(missing)}."
        )


def _prefixed(base: str, location: str | None) -> str:
    location = (location or "").strip("/")
    return f"{base}/{location}" if location else base


def _filesystem(storage) -> Repository:
    path = storage.location
    media_root = settings.MEDIA_ROOT
    # FileSystemStorage defaults to MEDIA_ROOT. A repository there would be
    # served under MEDIA_URL and swept into its own backup when MEDIA is on.
    if media_root and Path(path).resolve().is_relative_to(Path(media_root).resolve()):
        raise ImproperlyConfigured(
            f"RECOVERY['STORAGE'] resolves to {path!r}, inside MEDIA_ROOT. Give "
            "the FileSystemStorage alias its own 'location' outside MEDIA_ROOT."
        )
    return Repository(url=str(path))


def _s3(storage) -> Repository:
    _require(storage, "bucket_name")
    if bool(storage.access_key) != bool(storage.secret_key):
        raise ImproperlyConfigured(
            f"{_name(storage)} needs both access_key and secret_key, or neither "
            "(AWS default credential chain)."
        )
    endpoint = storage.endpoint_url or _DEFAULT_S3_ENDPOINT
    # restic defaults to HTTPS; an explicit http:// must survive so plain
    # HTTP endpoints (e.g. local MinIO) keep working.
    endpoint = endpoint.removeprefix("https://").rstrip("/")
    env = {}
    if storage.access_key:
        env["AWS_ACCESS_KEY_ID"] = storage.access_key
        env["AWS_SECRET_ACCESS_KEY"] = storage.secret_key
    if storage.session_profile:
        env["AWS_PROFILE"] = storage.session_profile
    if storage.region_name:
        env["AWS_DEFAULT_REGION"] = storage.region_name
    if storage.security_token:
        env["AWS_SESSION_TOKEN"] = storage.security_token
    url = _prefixed(f"s3:{endpoint}/{storage.bucket_name}", storage.location)
    return Repository(url=url, env=env)


def _gcs(storage) -> Repository:
    _require(storage, "bucket_name")
    if storage.custom_endpoint:
        raise _unsupported(storage, "custom_endpoint", "Use the default GCS endpoint.")
    # ``credentials`` is a google-auth object; restic can only read a key file
    # (GOOGLE_APPLICATION_CREDENTIALS) or use Application Default Credentials.
    if storage.credentials is not None and not os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    ):
        raise _unsupported(
            storage,
            "credentials",
            "Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to the "
            "service-account JSON key path, or drop GS_CREDENTIALS and use "
            "Application Default Credentials.",
        )
    env = {}
    if storage.project_id:
        env["GOOGLE_PROJECT_ID"] = storage.project_id
    location = (storage.location or "").strip("/")
    return Repository(url=f"gs:{storage.bucket_name}:/{location}", env=env)


def _azure(storage) -> Repository:
    if storage.connection_string:
        raise _unsupported(
            storage,
            "connection_string",
            "Configure account_name with account_key or sas_token instead.",
        )
    if storage.token_credential is not None:
        raise _unsupported(
            storage, "token_credential", "Use account_key or sas_token instead."
        )
    if not storage.azure_ssl:
        raise _unsupported(storage, "azure_ssl=False", "restic always uses HTTPS.")
    _require(storage, "azure_container", "account_name")
    if bool(storage.account_key) == bool(storage.sas_token):
        raise ImproperlyConfigured(
            f"{_name(storage)} needs exactly one of account_key or sas_token."
        )
    env = {"AZURE_ACCOUNT_NAME": storage.account_name}
    if storage.account_key:
        env["AZURE_ACCOUNT_KEY"] = storage.account_key
    else:
        env["AZURE_ACCOUNT_SAS"] = storage.sas_token
    if storage.endpoint_suffix and storage.endpoint_suffix != _DEFAULT_AZURE_SUFFIX:
        env["AZURE_ENDPOINT_SUFFIX"] = storage.endpoint_suffix
    location = (storage.location or "").strip("/")
    return Repository(url=f"azure:{storage.azure_container}:/{location}", env=env)


def _sftp(storage) -> Repository:
    params = storage.params or {}
    for key in ("password", "key_filename", "pkey"):
        if params.get(key):
            raise _unsupported(
                storage,
                f"params[{key!r}]",
                "restic authenticates through the system ssh client: configure "
                "the key in ~/.ssh/config or ssh-agent.",
            )
    _require(storage, "host", "root_path")
    user, port = params.get("username"), params.get("port")
    host = f"{user}@{storage.host}" if user else storage.host
    if port:
        # URL form: the path after the first "/" is relative to the login
        # home, so an absolute path yields "//abs" (restic's convention).
        return Repository(url=f"sftp://{host}:{port}/{storage.root_path}")
    return Repository(url=f"sftp:{host}:{storage.root_path}")


# dotted storage class path -> repository builder
_BUILDERS: dict[str, Callable[[object], Repository]] = {
    "django.core.files.storage.filesystem.FileSystemStorage": _filesystem,
    "storages.backends.s3.S3Storage": _s3,
    "storages.backends.gcloud.GoogleCloudStorage": _gcs,
    "storages.backends.azure_storage.AzureStorage": _azure,
    "storages.backends.sftpstorage.SFTPStorage": _sftp,
}


def repository_from_storage(storage) -> Repository:
    """Translate a Django storage instance into a restic :class:`Repository`.

    Raises:
        ImproperlyConfigured: for an unsupported storage class, a storage
            setting restic cannot honour, or a missing required setting.
    """
    for cls in type(storage).__mro__:
        build = _BUILDERS.get(f"{cls.__module__}.{cls.__qualname__}")
        if build:
            return build(storage)
    supported = ", ".join(sorted(_BUILDERS))
    raise ImproperlyConfigured(
        f"RECOVERY['STORAGE'] resolved to {type(storage).__module__}."
        f"{type(storage).__qualname__}, which has no restic equivalent. "
        f"Supported: {supported}."
    )
