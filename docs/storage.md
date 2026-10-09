# Storage

django-recovery keeps backups in one of your Django [`STORAGES`](https://docs.djangoproject.com/en/stable/ref/settings/#storages)
aliases. Point `RECOVERY['STORAGE']` at the alias; the restic repository URL and
credentials are read from that storage's resolved settings — including the global
`AWS_*` / `GS_*` / `AZURE_*` / `SFTP_*` settings django-storages falls back to.
Nothing is configured twice.

```python
STORAGES = {
    "default": {...},
    "staticfiles": {...},
    "backups": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {"bucket_name": "myapp-backups"},
    },
}

RECOVERY = {
    "STORAGE": "backups",
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
}
```

restic still performs every read and write; django-recovery only reads the storage's
settings. Installing and configuring the storage itself is your project's concern —
follow the [django-storages documentation](https://django-storages.readthedocs.io/)
for cloud backends.

!!! warning "Use a dedicated alias for backups"
    Reusing the media storage means the web app's credentials can also delete your
    backups. Prefer a separate bucket (ideally with object lock or write-only
    credentials). At minimum, give backups their own alias with a distinct prefix —
    credentials still come from the global settings:

    ```python
    "backups": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {"location": "restic"},   # same bucket as media, separate prefix
    },
    ```

## Supported storages

Subclasses of these classes are supported too (e.g. `class MediaStorage(S3Storage)`).
Settings with no restic equivalent raise `ImproperlyConfigured` rather than being
silently ignored; settings unrelated to the connection (ACLs, querystring auth, ...)
are ignored.

### Local directory — `django.core.files.storage.FileSystemStorage`

Django's built-in storage; no extra packages.

```python
"backups": {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": "/var/backups/myapp-restic"},
}
```

| Storage setting | Meaning |
|---|---|
| `location` | Repository directory. Must be **outside `MEDIA_ROOT`**. |

`FileSystemStorage` defaults to `MEDIA_ROOT`, so `location` is effectively required:
a repository inside `MEDIA_ROOT` would be served under `MEDIA_URL` and swept into its
own media backup.

### Amazon S3 and compatibles — `storages.backends.s3.S3Storage`

Also `S3Boto3Storage`. Works with R2, B2, Spaces, MinIO, Wasabi via `endpoint_url`.

| Storage setting | Meaning |
|---|---|
| `bucket_name` | Bucket name (required). |
| `location` | Key prefix inside the bucket. |
| `access_key` / `secret_key` | Static credentials (both or neither). |
| `security_token` | STS session token. |
| `session_profile` | Named profile from the AWS shared credentials file (`AWS_PROFILE`). |
| `endpoint_url` | S3-compatible endpoint; `http://` is kept for plain-HTTP MinIO. |
| `region_name` | Region. |

With no keys and no profile, restic uses the AWS default credential chain (IAM role,
instance profile, environment).

### Google Cloud Storage — `storages.backends.gcloud.GoogleCloudStorage`

| Storage setting | Meaning |
|---|---|
| `bucket_name` | Bucket name (required). |
| `location` | Prefix inside the bucket. |
| `project_id` | GCP project id. |

`GS_CREDENTIALS` is a Python credentials object restic cannot use. Rely on
Application Default Credentials (attached service account on GCE/GKE/Cloud Run —
recommended), or set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the
service-account JSON key path. `custom_endpoint` is not supported.

### Azure Blob Storage — `storages.backends.azure_storage.AzureStorage`

| Storage setting | Meaning |
|---|---|
| `azure_container` | Container name (required). |
| `account_name` | Storage account (required). |
| `account_key` / `sas_token` | Exactly one of the two. |
| `endpoint_suffix` | Sovereign clouds, e.g. `core.chinacloudapi.cn`. |
| `location` | Prefix inside the container. |

`connection_string`, `token_credential`, and `azure_ssl=False` are not supported.

### SFTP — `storages.backends.sftpstorage.SFTPStorage`

| Storage setting | Meaning |
|---|---|
| `host` | SSH host or `~/.ssh/config` alias (required). |
| `root_path` | Repository path; relative paths are relative to the login home (required). |
| `params['username']` | SSH user. |
| `params['port']` | SSH port. |

restic drives the system `ssh` client, so `params['password']`, `key_filename`, and
`pkey` are rejected: configure the key in `~/.ssh/config` or ssh-agent for the user
running Django.

## Not supported

Other storage classes (FTP, Dropbox, Apache Libcloud, in-memory, ...) have no restic
repository equivalent and raise `ImproperlyConfigured`.
