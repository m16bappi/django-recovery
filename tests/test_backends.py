"""Per-backend tests: repository URL building, env dict, option validation."""

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

PW = {"password": "pw"}


# --- base validation ---------------------------------------------------------

def test_unknown_option_raises():
    with pytest.raises(ImproperlyConfigured, match="Invalid option 'bucket'"):
        S3Backend(bucket="typo", access_key="a", secret_key="s", **PW)


def test_password_and_password_file_both_raise():
    with pytest.raises(ImproperlyConfigured, match="exactly one"):
        LocalBackend(path="/repo", password="pw", password_file="/f")


def test_neither_password_source_raises():
    with pytest.raises(ImproperlyConfigured, match="exactly one"):
        LocalBackend(path="/repo")


def test_password_file_goes_to_env():
    backend = LocalBackend(path="/repo", password_file="/etc/restic.pass")
    assert backend.env() == {"RESTIC_PASSWORD_FILE": "/etc/restic.pass"}


def test_base_repository_not_implemented():
    backend = BaseBackend(**PW)
    with pytest.raises(NotImplementedError):
        _ = backend.repository


# --- local -------------------------------------------------------------------

def test_local_repository_and_env():
    backend = LocalBackend(path="/var/backups/repo", **PW)
    assert backend.repository == "/var/backups/repo"
    assert backend.env() == {"RESTIC_PASSWORD": "pw"}


def test_local_requires_path():
    with pytest.raises(ImproperlyConfigured, match="path"):
        LocalBackend(**PW)


# --- s3 ------------------------------------------------------------------------

def test_s3_default_endpoint_and_env():
    backend = S3Backend(
        bucket_name="myapp-backups",
        access_key="AKIA123",
        secret_key="shhh",
        **PW,
    )
    assert backend.repository == "s3:s3.amazonaws.com/myapp-backups"
    assert backend.env() == {
        "AWS_ACCESS_KEY_ID": "AKIA123",
        "AWS_SECRET_ACCESS_KEY": "shhh",
        "RESTIC_PASSWORD": "pw",
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
        **PW,
    )
    assert backend.repository == "s3:accountid.r2.cloudflarestorage.com/b/prod"
    env = backend.env()
    assert env["AWS_DEFAULT_REGION"] == "auto"
    assert env["AWS_SESSION_TOKEN"] == "tok"


@pytest.mark.parametrize("missing", ["bucket_name", "access_key", "secret_key"])
def test_s3_missing_required_raises(missing):
    options = {"bucket_name": "b", "access_key": "a", "secret_key": "s", **PW}
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
        **PW,
    )
    assert backend.repository == "gs:myapp-backups:/prod"
    assert backend.env() == {
        "GOOGLE_PROJECT_ID": "my-project",
        "GOOGLE_APPLICATION_CREDENTIALS": "/etc/secrets/key.json",
        "RESTIC_PASSWORD": "pw",
    }


def test_gcs_adc_mode_no_credential_env():
    backend = GCSBackend(bucket_name="b", **PW)
    assert backend.repository == "gs:b:/"
    assert backend.env() == {"RESTIC_PASSWORD": "pw"}


def test_gcs_requires_bucket():
    with pytest.raises(ImproperlyConfigured, match="bucket_name"):
        GCSBackend(**PW)


# --- azure ----------------------------------------------------------------------

def test_azure_account_key_env():
    backend = AzureBackend(
        container="backups",
        account_name="acct",
        account_key="key123",
        location="prod",
        **PW,
    )
    assert backend.repository == "azure:backups:/prod"
    assert backend.env() == {
        "AZURE_ACCOUNT_NAME": "acct",
        "AZURE_ACCOUNT_KEY": "key123",
        "RESTIC_PASSWORD": "pw",
    }


def test_azure_sas_token_env():
    backend = AzureBackend(
        container="backups", account_name="acct", sas_token="sas123", **PW
    )
    assert backend.env()["AZURE_ACCOUNT_SAS"] == "sas123"
    assert "AZURE_ACCOUNT_KEY" not in backend.env()


def test_azure_key_and_sas_both_raise():
    with pytest.raises(ImproperlyConfigured, match="account_key.*sas_token"):
        AzureBackend(
            container="c", account_name="a", account_key="k", sas_token="s", **PW
        )


def test_azure_neither_key_nor_sas_raises():
    with pytest.raises(ImproperlyConfigured, match="account_key.*sas_token"):
        AzureBackend(container="c", account_name="a", **PW)


# --- sftp -----------------------------------------------------------------------

def test_sftp_repository_with_user():
    backend = SFTPBackend(host="backup.example.com", user="deploy",
                          path="/srv/restic", **PW)
    assert backend.repository == "sftp:deploy@backup.example.com:/srv/restic"


def test_sftp_repository_with_port_uses_url_form():
    backend = SFTPBackend(host="h", user="u", port=2222, path="/srv/restic", **PW)
    assert backend.repository == "sftp://u@h:2222/srv/restic"


def test_sftp_requires_host_and_path():
    with pytest.raises(ImproperlyConfigured):
        SFTPBackend(host="h", **PW)


# --- generic ---------------------------------------------------------------------

def test_generic_repository_verbatim_with_env_passthrough():
    backend = GenericBackend(
        repository="rclone:mydropbox:backups",
        extra_env={"RCLONE_CONFIG": "/etc/rclone.conf"},
        **PW,
    )
    assert backend.repository == "rclone:mydropbox:backups"
    assert backend.env() == {
        "RCLONE_CONFIG": "/etc/rclone.conf",
        "RESTIC_PASSWORD": "pw",
    }


def test_generic_requires_repository():
    with pytest.raises(ImproperlyConfigured, match="repository"):
        GenericBackend(**PW)
