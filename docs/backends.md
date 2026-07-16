# Storage backends

Pick the class matching where the repository lives. Each accepts the
[common options](configuration.md#common-backend-options) (`location` where noted)
plus its own. Unknown or missing options raise `ImproperlyConfigured` with the
valid option list.

Examples below show `OPTIONS` only. The repository password is configured
separately — see [Repository password](configuration.md#repository-password).

## Local directory

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {
        "path": "/var/backups/myapp-restic",
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `path` | yes | Directory for the repository. |

## Amazon S3 — and R2, B2, Spaces, MinIO, Wasabi, ...

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.S3Backend",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "location": "prod",
        "access_key": os.environ["AWS_KEY_ID"],
        "secret_key": os.environ["AWS_SECRET"],
        "region_name": "eu-central-1",
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `bucket_name` | yes | Bucket name. |
| `access_key` | yes | Access key id. |
| `secret_key` | yes | Secret access key. |
| `endpoint_url` | no | S3-compatible endpoint; defaults to AWS (`s3.amazonaws.com`). |
| `region_name` | no | Region. |
| `session_token` | no | STS session token for temporary credentials. |
| `location` | no | Key prefix inside the bucket. |

Any S3-compatible service works by pointing `endpoint_url` at it:

```python
"endpoint_url": "https://<accountid>.r2.cloudflarestorage.com",   # Cloudflare R2
"endpoint_url": "https://s3.us-west-000.backblazeb2.com",         # Backblaze B2
"endpoint_url": "https://fra1.digitaloceanspaces.com",            # DO Spaces
"endpoint_url": "http://minio.internal:9000",                     # MinIO
```

## Google Cloud Storage

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.GCSBackend",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "location": "prod",
        "project_id": "my-project-123456",
        "credentials_file": "/etc/secrets/gcs-key.json",
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `bucket_name` | yes | Bucket name. |
| `project_id` | no | GCP project id. |
| `credentials_file` | no | Service-account JSON key path. **Omit on GCE/GKE/Cloud Run** to use the attached service account (Application Default Credentials) — the recommended production setup. |
| `location` | no | Prefix inside the bucket. |

The service account needs `Storage Object Admin` on the bucket (or `Storage Admin` if
`recovery init` should create the bucket).

## Azure Blob Storage

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.AzureBackend",
    "OPTIONS": {
        "container": "backups",
        "location": "prod",
        "account_name": "myaccount",
        "account_key": os.environ["AZURE_KEY"],
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `container` | yes | Blob container name. |
| `account_name` | yes | Storage account name. |
| `account_key` | one of | Account access key. |
| `sas_token` | one of | SAS token — provide this **or** `account_key`. |
| `location` | no | Prefix inside the container. |

## SFTP

Key/agent authentication only — restic drives the system `ssh`, so password
authentication is not supported. Configure the host in `~/.ssh/config` or load a key
into the agent for the user running Django.

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.SFTPBackend",
    "OPTIONS": {
        "host": "backup.example.com",
        "user": "deploy",
        "path": "/srv/restic/myapp",
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `host` | yes | SSH host (or `~/.ssh/config` alias). |
| `path` | yes | Repository path on the server. |
| `user` | no | SSH user. |
| `port` | no | SSH port. |

## Anything else — rclone, rest-server, Swift

`GenericBackend` passes a raw restic repository URL through verbatim, with optional
extra environment variables for the subprocess:

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.GenericBackend",
    "OPTIONS": {
        "repository": "rclone:mydropbox:backups/myapp",
        "extra_env": {"RCLONE_CONFIG": "/etc/rclone.conf"},
    },
}
```

| Option | Required | Meaning |
|---|---|---|
| `repository` | yes | Any restic repository URL: `rclone:...`, `rest:https://...`, `swift:...`. |
| `extra_env` | no | Extra env vars merged into the restic subprocess environment. |

With rclone, restic reaches [everything rclone supports](https://rclone.org/overview/)
— Dropbox, Google Drive, OneDrive, and ~70 more.
