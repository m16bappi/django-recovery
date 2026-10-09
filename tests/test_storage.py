"""``RECOVERY['STORAGE']``: deriving the restic repository from a Django storage.

django-storages and its provider SDKs are not test dependencies: storage
classes are matched by dotted path along the MRO, so lightweight fakes whose
``__module__``/``__qualname__`` match the real classes exercise the mapping
faithfully. One test against the real ``S3Storage`` runs when installed.
"""

import os

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from django.test import override_settings

from django_recovery.conf import get_config
from django_recovery.storage import Repository, repository_from_storage


def _fake_storage(dotted: str, defaults: dict) -> type:
    """A stand-in for a django-storages class at ``dotted`` with ``defaults``."""
    module, name = dotted.rsplit(".", 1)

    def __init__(self, **settings):
        self.__dict__.update({**defaults, **settings})

    cls = type(name, (), {"__init__": __init__})
    cls.__module__ = module
    cls.__qualname__ = name
    return cls


FakeS3Storage = _fake_storage(
    "storages.backends.s3.S3Storage",
    {
        "bucket_name": None,
        "access_key": None,
        "secret_key": None,
        "security_token": None,
        "session_profile": None,
        "endpoint_url": None,
        "region_name": None,
        "location": "",
        "querystring_auth": True,  # unrelated setting: must be ignored
    },
)

FakeGCSStorage = _fake_storage(
    "storages.backends.gcloud.GoogleCloudStorage",
    {
        "bucket_name": None,
        "project_id": None,
        "credentials": None,
        "custom_endpoint": None,
        "location": "",
    },
)

FakeAzureStorage = _fake_storage(
    "storages.backends.azure_storage.AzureStorage",
    {
        "account_name": None,
        "account_key": None,
        "sas_token": None,
        "azure_container": None,
        "azure_ssl": True,
        "connection_string": None,
        "token_credential": None,
        "endpoint_suffix": "core.windows.net",
        "location": "",
    },
)

FakeSFTPStorage = _fake_storage(
    "storages.backends.sftpstorage.SFTPStorage",
    {"host": None, "params": {}, "root_path": ""},
)

FakeFTPStorage = _fake_storage("storages.backends.ftp.FTPStorage", {})


# --- filesystem (Django built-in) ---------------------------------------------

def test_filesystem_storage_maps_to_local_repo(tmp_path):
    repo = tmp_path / "repo"
    assert repository_from_storage(FileSystemStorage(location=repo)) == Repository(
        url=os.path.abspath(repo)
    )


def test_filesystem_storage_inside_media_root_rejected(tmp_path):
    media = tmp_path / "media"
    with override_settings(MEDIA_ROOT=str(media)):
        # No location: FileSystemStorage defaults to MEDIA_ROOT itself.
        with pytest.raises(ImproperlyConfigured, match="inside MEDIA_ROOT"):
            repository_from_storage(FileSystemStorage())
        with pytest.raises(ImproperlyConfigured, match="inside MEDIA_ROOT"):
            repository_from_storage(FileSystemStorage(location=media / "restic"))


# --- s3 -----------------------------------------------------------------------

def test_s3_default_endpoint_and_keys():
    storage = FakeS3Storage(bucket_name="myapp-backups", access_key="AKIA",
                            secret_key="shhh")
    assert repository_from_storage(storage) == Repository(
        url="s3:s3.amazonaws.com/myapp-backups",
        env={"AWS_ACCESS_KEY_ID": "AKIA", "AWS_SECRET_ACCESS_KEY": "shhh"},
    )


def test_s3_custom_endpoint_location_region_token():
    storage = FakeS3Storage(
        bucket_name="b",
        access_key="a",
        secret_key="s",
        security_token="tok",
        endpoint_url="https://accountid.r2.cloudflarestorage.com/",
        region_name="auto",
        location="prod/",
    )
    repo = repository_from_storage(storage)
    assert repo.url == "s3:accountid.r2.cloudflarestorage.com/b/prod"
    assert repo.env["AWS_DEFAULT_REGION"] == "auto"
    assert repo.env["AWS_SESSION_TOKEN"] == "tok"


def test_s3_http_endpoint_scheme_preserved():
    storage = FakeS3Storage(bucket_name="b", endpoint_url="http://minio:9000/")
    assert repository_from_storage(storage).url == "s3:http://minio:9000/b"


def test_s3_session_profile_maps_to_aws_profile():
    storage = FakeS3Storage(bucket_name="b", session_profile="backups")
    assert repository_from_storage(storage).env == {"AWS_PROFILE": "backups"}


def test_s3_iam_role_no_keys():
    assert repository_from_storage(FakeS3Storage(bucket_name="b")).env == {}


def test_s3_single_key_rejected():
    storage = FakeS3Storage(bucket_name="b", access_key="a")
    with pytest.raises(ImproperlyConfigured, match="access_key and secret_key"):
        repository_from_storage(storage)


def test_s3_bucket_required():
    with pytest.raises(ImproperlyConfigured, match="bucket_name"):
        repository_from_storage(FakeS3Storage())


def test_subclass_of_supported_storage_matches():
    class MediaStorage(FakeS3Storage):
        pass

    assert repository_from_storage(MediaStorage(bucket_name="b")).url.startswith("s3:")


# --- gcs ----------------------------------------------------------------------

def test_gcs_adc():
    storage = FakeGCSStorage(bucket_name="b", project_id="p", location="prod")
    assert repository_from_storage(storage) == Repository(
        url="gs:b:/prod", env={"GOOGLE_PROJECT_ID": "p"}
    )


def test_gcs_no_location():
    assert repository_from_storage(FakeGCSStorage(bucket_name="b")).url == "gs:b:/"


def test_gcs_credentials_object_rejected_without_key_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    storage = FakeGCSStorage(bucket_name="b", credentials=object())
    with pytest.raises(ImproperlyConfigured, match="GOOGLE_APPLICATION_CREDENTIALS"):
        repository_from_storage(storage)


def test_gcs_credentials_object_allowed_with_key_file_env(monkeypatch):
    # restic inherits GOOGLE_APPLICATION_CREDENTIALS from the environment.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/k.json")
    storage = FakeGCSStorage(bucket_name="b", credentials=object())
    assert repository_from_storage(storage).url == "gs:b:/"


def test_gcs_custom_endpoint_rejected():
    storage = FakeGCSStorage(bucket_name="b", custom_endpoint="https://cdn")
    with pytest.raises(ImproperlyConfigured, match="custom_endpoint"):
        repository_from_storage(storage)


# --- azure --------------------------------------------------------------------

def test_azure_account_key():
    storage = FakeAzureStorage(
        account_name="acct", account_key="key", azure_container="c", location="x"
    )
    # default public-cloud suffix is not forwarded
    assert repository_from_storage(storage) == Repository(
        url="azure:c:/x",
        env={"AZURE_ACCOUNT_NAME": "acct", "AZURE_ACCOUNT_KEY": "key"},
    )


def test_azure_sas_token_and_sovereign_suffix():
    storage = FakeAzureStorage(
        account_name="a", sas_token="sas", azure_container="c",
        endpoint_suffix="core.chinacloudapi.cn",
    )
    env = repository_from_storage(storage).env
    assert env["AZURE_ACCOUNT_SAS"] == "sas"
    assert "AZURE_ACCOUNT_KEY" not in env
    assert env["AZURE_ENDPOINT_SUFFIX"] == "core.chinacloudapi.cn"


@pytest.mark.parametrize("auth", [{}, {"account_key": "k", "sas_token": "s"}])
def test_azure_needs_exactly_one_of_key_or_sas(auth):
    storage = FakeAzureStorage(account_name="a", azure_container="c", **auth)
    with pytest.raises(ImproperlyConfigured, match="account_key or sas_token"):
        repository_from_storage(storage)


def test_azure_container_required():
    storage = FakeAzureStorage(account_name="a", account_key="k")
    with pytest.raises(ImproperlyConfigured, match="azure_container"):
        repository_from_storage(storage)


@pytest.mark.parametrize(
    "setting, value",
    [
        ("connection_string", "AccountName=a;AccountKey=k"),
        ("token_credential", object()),
        ("azure_ssl", False),
    ],
)
def test_azure_unmappable_settings_rejected(setting, value):
    storage = FakeAzureStorage(
        account_name="a", account_key="k", azure_container="c", **{setting: value}
    )
    with pytest.raises(ImproperlyConfigured, match=setting):
        repository_from_storage(storage)


# --- sftp ---------------------------------------------------------------------

def test_sftp_without_port():
    storage = FakeSFTPStorage(host="backup.example.com", root_path="/srv/restic",
                              params={"username": "deploy"})
    assert repository_from_storage(storage) == Repository(
        url="sftp:deploy@backup.example.com:/srv/restic"
    )


def test_sftp_port_keeps_absolute_path():
    # restic URL form: "//" after host:port means an absolute path.
    storage = FakeSFTPStorage(host="h", root_path="/srv/restic",
                              params={"username": "u", "port": 2222})
    assert repository_from_storage(storage).url == "sftp://u@h:2222//srv/restic"


def test_sftp_port_relative_path():
    storage = FakeSFTPStorage(host="h", root_path="backups", params={"port": 2222})
    assert repository_from_storage(storage).url == "sftp://h:2222/backups"


def test_sftp_host_and_root_path_required():
    with pytest.raises(ImproperlyConfigured, match="root_path"):
        repository_from_storage(FakeSFTPStorage(host="h"))


@pytest.mark.parametrize("key", ["password", "key_filename", "pkey"])
def test_sftp_non_ssh_auth_rejected(key):
    storage = FakeSFTPStorage(host="h", root_path="/r", params={key: "x"})
    with pytest.raises(ImproperlyConfigured, match=key):
        repository_from_storage(storage)


# --- unsupported --------------------------------------------------------------

def test_unsupported_storage_class_rejected():
    with pytest.raises(ImproperlyConfigured, match="no restic equivalent"):
        repository_from_storage(FakeFTPStorage())


# --- conf integration ---------------------------------------------------------

_STORAGES = {
    "backups": {
        "BACKEND": "tests.test_storage.FakeS3Storage",
        "OPTIONS": {"bucket_name": "myapp-backups", "access_key": "a",
                    "secret_key": "s", "location": "restic"},
    },
}


def test_get_config_storage_alias():
    with override_settings(STORAGES=_STORAGES,
                           RECOVERY={"STORAGE": "backups", "PASSWORD": "pw"}):
        config = get_config()
    assert config.repository.url == "s3:s3.amazonaws.com/myapp-backups/restic"
    assert config.restic_env() == {
        "AWS_ACCESS_KEY_ID": "a",
        "AWS_SECRET_ACCESS_KEY": "s",
        "RESTIC_PASSWORD": "pw",
    }


def test_get_config_unknown_storage_alias():
    with override_settings(STORAGES=_STORAGES, RECOVERY={"STORAGE": "nope"}):
        with pytest.raises(ImproperlyConfigured, match="'nope'"):
            get_config()


def test_get_config_storage_import_error():
    storages = {"broken": {"BACKEND": "storages.backends.does_not_exist.Nope"}}
    with override_settings(STORAGES=storages, RECOVERY={"STORAGE": "broken"}):
        with pytest.raises(ImproperlyConfigured, match="could not be loaded"):
            get_config()


# --- real django-storages -----------------------------------------------------

def test_real_s3storage_resolves_global_aws_settings():
    pytest.importorskip("boto3")
    s3 = pytest.importorskip("storages.backends.s3")
    with override_settings(AWS_ACCESS_KEY_ID="AKIA", AWS_SECRET_ACCESS_KEY="shhh",
                           AWS_STORAGE_BUCKET_NAME="media", AWS_LOCATION="restic",
                           AWS_S3_ENDPOINT_URL="http://minio:9000"):
        repo = repository_from_storage(s3.S3Storage())
    assert repo.url == "s3:http://minio:9000/media/restic"
    assert repo.env["AWS_ACCESS_KEY_ID"] == "AKIA"


def test_s3_use_ssl_false_without_scheme_uses_http():
    storage = FakeS3Storage(bucket_name="b", endpoint_url="minio:9000", use_ssl=False)
    assert repository_from_storage(storage).url == "s3:http://minio:9000/b"


def test_s3_use_ssl_false_keeps_explicit_scheme():
    storage = FakeS3Storage(bucket_name="b", endpoint_url="https://minio:9000",
                            use_ssl=False)
    assert repository_from_storage(storage).url == "s3:minio:9000/b"
