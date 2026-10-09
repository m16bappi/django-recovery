"""``RECOVERY['STORAGE']``: deriving the restic repository from a Django storage.

django-storages and its provider SDKs are not test dependencies. Storage
classes are matched by dotted path along the MRO, so small fakes whose
``__module__``/``__qualname__`` match the real classes exercise the mapping
faithfully. One test uses the real ``S3Storage`` when it is installed.
"""

import os

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage

from django_recovery.conf import get_config
from django_recovery.storage import Repository, repository_from_storage


def fake_storage(dotted: str, **defaults) -> type:
    """A stand-in for the storage class at ``dotted``, with default settings."""
    module, name = dotted.rsplit(".", 1)

    def __init__(self, **settings):
        self.__dict__.update({**defaults, **settings})

    return type(name, (), {"__init__": __init__, "__module__": module, "__qualname__": name})


FakeS3Storage = fake_storage(
    "storages.backends.s3.S3Storage",
    bucket_name=None, access_key=None, secret_key=None, security_token=None,
    session_profile=None, endpoint_url=None, region_name=None, location="",
    use_ssl=True, querystring_auth=True,  # unrelated settings are ignored
)
FakeGCSStorage = fake_storage(
    "storages.backends.gcloud.GoogleCloudStorage",
    bucket_name=None, project_id=None, credentials=None, custom_endpoint=None, location="",
)
FakeAzureStorage = fake_storage(
    "storages.backends.azure_storage.AzureStorage",
    account_name=None, account_key=None, sas_token=None, azure_container=None,
    azure_ssl=True, connection_string=None, token_credential=None,
    endpoint_suffix="core.windows.net", location="",
)
FakeSFTPStorage = fake_storage(
    "storages.backends.sftpstorage.SFTPStorage", host=None, params={}, root_path="",
)
FakeFTPStorage = fake_storage("storages.backends.ftp.FTPStorage")


class MediaStorage(FakeS3Storage):
    """A project subclass: must map like its parent."""


S3_KEYS = {"access_key": "AKIA", "secret_key": "shhh"}
S3_KEY_ENV = {"AWS_ACCESS_KEY_ID": "AKIA", "AWS_SECRET_ACCESS_KEY": "shhh"}
AZ = {"account_name": "acct", "azure_container": "c"}


# --- supported storages --------------------------------------------------------

@pytest.mark.parametrize("storage, url, env", [
    # S3
    pytest.param(FakeS3Storage(bucket_name="b", **S3_KEYS),
                 "s3:s3.amazonaws.com/b", S3_KEY_ENV, id="s3-defaults"),
    pytest.param(FakeS3Storage(bucket_name="b", endpoint_url="https://r2.example.com/",
                               location="/prod/", region_name="auto", security_token="tok",
                               **S3_KEYS),
                 "s3:r2.example.com/b/prod",
                 {**S3_KEY_ENV, "AWS_DEFAULT_REGION": "auto", "AWS_SESSION_TOKEN": "tok"},
                 id="s3-endpoint-location-region-token"),
    pytest.param(FakeS3Storage(bucket_name="b", endpoint_url="http://minio:9000/"),
                 "s3:http://minio:9000/b", {}, id="s3-http-kept"),
    pytest.param(FakeS3Storage(bucket_name="b", endpoint_url="minio:9000", use_ssl=False),
                 "s3:http://minio:9000/b", {}, id="s3-use_ssl-false"),
    pytest.param(FakeS3Storage(bucket_name="b", endpoint_url="https://m:9000", use_ssl=False),
                 "s3:m:9000/b", {}, id="s3-use_ssl-false-explicit-https"),
    pytest.param(FakeS3Storage(bucket_name="b", session_profile="backups"),
                 "s3:s3.amazonaws.com/b", {"AWS_PROFILE": "backups"}, id="s3-profile"),
    pytest.param(FakeS3Storage(bucket_name="b"),
                 "s3:s3.amazonaws.com/b", {}, id="s3-iam-role"),
    pytest.param(MediaStorage(bucket_name="b"),
                 "s3:s3.amazonaws.com/b", {}, id="s3-subclass"),
    # Google Cloud Storage
    pytest.param(FakeGCSStorage(bucket_name="b", project_id="p", location="prod"),
                 "gs:b:/prod", {"GOOGLE_PROJECT_ID": "p"}, id="gcs"),
    pytest.param(FakeGCSStorage(bucket_name="b"), "gs:b:/", {}, id="gcs-no-location"),
    # Azure (the default public-cloud suffix is not forwarded)
    pytest.param(FakeAzureStorage(account_key="key", location="x", **AZ),
                 "azure:c:/x", {"AZURE_ACCOUNT_NAME": "acct", "AZURE_ACCOUNT_KEY": "key"},
                 id="azure-key"),
    pytest.param(FakeAzureStorage(sas_token="sas", endpoint_suffix="core.chinacloudapi.cn", **AZ),
                 "azure:c:/",
                 {"AZURE_ACCOUNT_NAME": "acct", "AZURE_ACCOUNT_SAS": "sas",
                  "AZURE_ENDPOINT_SUFFIX": "core.chinacloudapi.cn"},
                 id="azure-sas-sovereign-cloud"),
    # SFTP ("//" after host:port means an absolute path)
    pytest.param(FakeSFTPStorage(host="example.com", root_path="/srv/restic",
                                 params={"username": "deploy"}),
                 "sftp:deploy@example.com:/srv/restic", {}, id="sftp"),
    pytest.param(FakeSFTPStorage(host="h", root_path="/srv/restic",
                                 params={"username": "u", "port": 2222}),
                 "sftp://u@h:2222//srv/restic", {}, id="sftp-port-absolute"),
    pytest.param(FakeSFTPStorage(host="h", root_path="backups", params={"port": 2222}),
                 "sftp://h:2222/backups", {}, id="sftp-port-relative"),
])
def test_repository(storage, url, env):
    assert repository_from_storage(storage) == Repository(url=url, env=env)


def test_gcs_credentials_object_allowed_with_key_file_env(monkeypatch):
    # restic reads the key file from GOOGLE_APPLICATION_CREDENTIALS itself.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/k.json")
    storage = FakeGCSStorage(bucket_name="b", credentials=object())
    assert repository_from_storage(storage).url == "gs:b:/"


def test_filesystem_storage_maps_to_local_repo(tmp_path):
    storage = FileSystemStorage(location=tmp_path / "repo")
    assert repository_from_storage(storage) == Repository(url=os.path.abspath(tmp_path / "repo"))


# --- rejected configurations -----------------------------------------------------------

@pytest.mark.parametrize("storage, match", [
    pytest.param(FakeS3Storage(), "bucket_name", id="s3-no-bucket"),
    pytest.param(FakeS3Storage(bucket_name="b", access_key="a"),
                 "access_key and secret_key", id="s3-one-key"),
    pytest.param(FakeGCSStorage(bucket_name="b", custom_endpoint="https://cdn"),
                 "custom_endpoint", id="gcs-custom-endpoint"),
    pytest.param(FakeAzureStorage(**AZ), "account_key or sas_token", id="azure-no-auth"),
    pytest.param(FakeAzureStorage(account_key="k", sas_token="s", **AZ),
                 "account_key or sas_token", id="azure-both-auth"),
    pytest.param(FakeAzureStorage(account_name="a", account_key="k"),
                 "azure_container", id="azure-no-container"),
    *[pytest.param(FakeAzureStorage(account_key="k", **AZ, **{key: value}), key,
                   id=f"azure-{key}")
      for key, value in (("connection_string", "AccountName=a"),
                         ("token_credential", object()), ("azure_ssl", False))],
    pytest.param(FakeSFTPStorage(host="h"), "root_path", id="sftp-no-root-path"),
    *[pytest.param(FakeSFTPStorage(host="h", root_path="/r", params={key: "x"}), key,
                   id=f"sftp-{key}")
      for key in ("password", "key_filename", "pkey")],
    pytest.param(FakeFTPStorage(), "no restic equivalent", id="unsupported-class"),
])
def test_rejected(storage, match):
    with pytest.raises(ImproperlyConfigured, match=match):
        repository_from_storage(storage)


def test_gcs_credentials_object_rejected_without_key_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(ImproperlyConfigured, match="GOOGLE_APPLICATION_CREDENTIALS"):
        repository_from_storage(FakeGCSStorage(bucket_name="b", credentials=object()))


@pytest.mark.parametrize("location", [None, "restic"])
def test_filesystem_storage_inside_media_root_rejected(settings, tmp_path, location):
    media = tmp_path / "media"
    settings.MEDIA_ROOT = str(media)
    # No location: FileSystemStorage defaults to MEDIA_ROOT itself.
    storage = FileSystemStorage(location=media / location) if location else FileSystemStorage()
    with pytest.raises(ImproperlyConfigured, match="inside MEDIA_ROOT"):
        repository_from_storage(storage)


# --- through get_config() -------------------------------------------------------------

def test_get_config_uses_the_named_storage(settings, recovery):
    settings.STORAGES = {"backups": {
        "BACKEND": "tests.test_storage.FakeS3Storage",
        "OPTIONS": {"bucket_name": "myapp-backups", "location": "restic", **S3_KEYS},
    }}
    recovery(STORAGE="backups", PASSWORD="pw")
    config = get_config()
    assert config.repository.url == "s3:s3.amazonaws.com/myapp-backups/restic"
    assert config.restic_env() == {**S3_KEY_ENV, "RESTIC_PASSWORD": "pw"}


@pytest.mark.parametrize("storages, alias, match", [
    ({}, "nope", "'nope' could not be loaded"),
    ({"broken": {"BACKEND": "storages.backends.does_not_exist.Nope"}}, "broken",
     "'broken' could not be loaded"),
])
def test_get_config_storage_that_cannot_load(settings, recovery, storages, alias, match):
    settings.STORAGES = storages
    recovery(STORAGE=alias)
    with pytest.raises(ImproperlyConfigured, match=match):
        get_config()


# --- real django-storages ----------------------------------------------------------------

def test_real_s3storage_resolves_global_aws_settings(settings):
    pytest.importorskip("boto3")
    s3 = pytest.importorskip("storages.backends.s3")
    settings.AWS_ACCESS_KEY_ID = "AKIA"
    settings.AWS_SECRET_ACCESS_KEY = "shhh"
    settings.AWS_STORAGE_BUCKET_NAME = "media"
    settings.AWS_LOCATION = "restic"
    settings.AWS_S3_ENDPOINT_URL = "http://minio:9000"
    repo = repository_from_storage(s3.S3Storage())
    assert repo.url == "s3:http://minio:9000/media/restic"
    assert repo.env["AWS_ACCESS_KEY_ID"] == "AKIA"
