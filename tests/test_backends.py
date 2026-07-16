"""Per-backend tests: repository URL building, env dict, option validation.

Backends carry connection details only. The repository password lives in the
top-level ``RECOVERY['PASSWORD']`` / ``'PASSWORD_FILE'`` keys and is tested
with the config layer in ``test_conf.py``.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_recovery.backends import (
    AzureBackend,
    BaseBackend,
    GCSBackend,
    GenericBackend,
    LocalBackend,
    S3Backend,
    SFTPBackend,
)


# --- base validation ---------------------------------------------------------

def test_unknown_option_raises():
    with pytest.raises(ImproperlyConfigured, match="Invalid option 'bucket'"):
        S3Backend(bucket="typo", access_key="a", secret_key="s")


def test_password_is_not_a_backend_option():
    with pytest.raises(ImproperlyConfigured, match="Invalid option 'password'"):
        LocalBackend(path="/repo", password="pw")


def test_base_backend_is_abstract():
    with pytest.raises(TypeError, match="abstract"):
        BaseBackend()


def test_base_repository_not_implemented():
    class Dummy(BaseBackend):
        def get_default_options(self):
            return {}

    with pytest.raises(NotImplementedError):
        _ = Dummy().repository


def test_location_rejected_where_not_supported():
    # Only the bucket/container backends declare 'location'.
    with pytest.raises(ImproperlyConfigured, match="Invalid option 'location'"):
        LocalBackend(path="/repo", location="prod")


# --- local -------------------------------------------------------------------

def test_local_repository_and_env():
    backend = LocalBackend(path="/var/backups/repo")
    assert backend.repository == "/var/backups/repo"
    assert backend.env() == {}


def test_local_requires_path():
    with pytest.raises(ImproperlyConfigured, match="path"):
        LocalBackend()


# --- s3 ------------------------------------------------------------------------

def test_s3_default_endpoint_and_env():
    backend = S3Backend(
        bucket_name="myapp-backups",
        access_key="AKIA123",
        secret_key="shhh",
    )
    assert backend.repository == "s3:s3.amazonaws.com/myapp-backups"
    assert backend.env() == {
        "AWS_ACCESS_KEY_ID": "AKIA123",
        "AWS_SECRET_ACCESS_KEY": "shhh",
    }


def test_s3_custom_endpoint_location_region_token():
    backend = S3Backend(
        bucket_name="b",
        access_key="a",
        secret_key="s",
        endpoint_url="https://accountid.r2.cloudflarestorage.com/",
        location="/prod/",
        region_name="auto",
        session_token="tok",
    )
    assert backend.repository == "s3:accountid.r2.cloudflarestorage.com/b/prod"
    env = backend.env()
    assert env["AWS_DEFAULT_REGION"] == "auto"
    assert env["AWS_SESSION_TOKEN"] == "tok"


@pytest.mark.parametrize("missing", ["bucket_name", "access_key", "secret_key"])
def test_s3_missing_required_raises(missing):
    options = {"bucket_name": "b", "access_key": "a", "secret_key": "s"}
    del options[missing]
    with pytest.raises(ImproperlyConfigured, match=missing):
        S3Backend(**options)


# --- gcs -----------------------------------------------------------------------

def test_gcs_repository_and_env():
    backend = GCSBackend(
        bucket_name="myapp-backups",
        project_id="my-project",
        credentials_file="/etc/secrets/key.json",
        location="prod",
    )
    assert backend.repository == "gs:myapp-backups:/prod"
    assert backend.env() == {
        "GOOGLE_PROJECT_ID": "my-project",
        "GOOGLE_APPLICATION_CREDENTIALS": "/etc/secrets/key.json",
    }


def test_gcs_adc_mode_no_credential_env_vars():
    backend = GCSBackend(bucket_name="b")
    assert backend.repository == "gs:b:/"
    assert backend.env() == {}


def test_gcs_requires_bucket():
    with pytest.raises(ImproperlyConfigured, match="bucket_name"):
        GCSBackend()


# --- azure ----------------------------------------------------------------------

def test_azure_account_key_env():
    backend = AzureBackend(
        container="backups",
        account_name="acct",
        account_key="key123",
        location="prod",
    )
    assert backend.repository == "azure:backups:/prod"
    assert backend.env() == {
        "AZURE_ACCOUNT_NAME": "acct",
        "AZURE_ACCOUNT_KEY": "key123",
    }


def test_azure_sas_token_env():
    backend = AzureBackend(container="backups", account_name="acct", sas_token="sas123")
    assert backend.env()["AZURE_ACCOUNT_SAS"] == "sas123"
    assert "AZURE_ACCOUNT_KEY" not in backend.env()


def test_azure_key_and_sas_both_raise():
    with pytest.raises(ImproperlyConfigured, match="account_key.*sas_token"):
        AzureBackend(container="c", account_name="a", account_key="k", sas_token="s")


def test_azure_neither_key_nor_sas_raises():
    with pytest.raises(ImproperlyConfigured, match="account_key.*sas_token"):
        AzureBackend(container="c", account_name="a")


# --- sftp -----------------------------------------------------------------------

def test_sftp_repository_with_user():
    backend = SFTPBackend(host="backup.example.com", user="deploy",
                          path="/srv/restic")
    assert backend.repository == "sftp:deploy@backup.example.com:/srv/restic"


def test_sftp_repository_with_port_uses_url_form():
    backend = SFTPBackend(host="h", user="u", port=2222, path="/srv/restic")
    assert backend.repository == "sftp://u@h:2222/srv/restic"


def test_sftp_requires_host_and_path():
    with pytest.raises(ImproperlyConfigured):
        SFTPBackend(host="h")


# --- generic ---------------------------------------------------------------------

def test_generic_repository_verbatim_with_env_passthrough():
    backend = GenericBackend(
        repository="rclone:mydropbox:backups",
        extra_env={"RCLONE_CONFIG": "/etc/rclone.conf"},
    )
    assert backend.repository == "rclone:mydropbox:backups"
    assert backend.env() == {"RCLONE_CONFIG": "/etc/rclone.conf"}


def test_generic_requires_repository():
    with pytest.raises(ImproperlyConfigured, match="repository"):
        GenericBackend()
