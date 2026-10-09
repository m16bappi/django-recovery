# Storage

Backups go to one of your Django `STORAGES`. Give it a name, then put that name in
`RECOVERY["STORAGE"]`:

```python
RECOVERY = {"STORAGE": "backups", "PASSWORD": os.environ["RESTIC_PASSWORD"]}
```

django-recovery reads the bucket, folder, and credentials from that storage. You do not
write them twice. For cloud storage, install and set up
[django-storages](https://django-storages.readthedocs.io/) as you normally would.

!!! warning "Use a separate storage for backups"
    If backups share the media bucket and its keys, anyone who gets those keys can
    delete your backups too. Use a separate bucket if you can. At least use a separate
    folder (`location`) — see the S3 example below.

## Local folder

```python
"backups": {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": "/var/backups/myapp"},
}
```

The folder must be **outside `MEDIA_ROOT`**, or django-recovery stops with an error.

## Amazon S3 (and R2, B2, MinIO, Spaces, Wasabi)

```python
"backups": {
    "BACKEND": "storages.backends.s3.S3Storage",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "location": "restic",                      # optional folder in the bucket
        # "endpoint_url": "http://minio:9000",     # for S3-compatible services
    },
}
```

Keys come from the storage options or your `AWS_*` settings. With no keys, restic uses
the server's IAM role. `session_profile` (an AWS profile name) also works.

## Google Cloud Storage

```python
"backups": {
    "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    "OPTIONS": {"bucket_name": "myapp-backups", "location": "restic"},
}
```

On Google Cloud (GCE, GKE, Cloud Run) it uses the attached service account — nothing
else to do. Elsewhere, set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to
your key file. (A `GS_CREDENTIALS` object alone is not enough for restic.)

## Azure Blob Storage

```python
"backups": {
    "BACKEND": "storages.backends.azure_storage.AzureStorage",
    "OPTIONS": {
        "azure_container": "backups",
        "account_name": "myaccount",
        "account_key": os.environ["AZURE_KEY"],   # or "sas_token"
    },
}
```

Use `account_key` **or** `sas_token`. `connection_string` and `token_credential` are not
supported.

## SFTP

```python
"backups": {
    "BACKEND": "storages.backends.sftpstorage.SFTPStorage",
    "OPTIONS": {
        "host": "backup.example.com",
        "root_path": "/srv/backups/myapp",
        "params": {"username": "deploy", "port": 22},
    },
}
```

restic uses your system `ssh`, so log in with an SSH key set up in `~/.ssh/config` or
ssh-agent. Passwords and `key_filename` in `params` are not supported.

## Anything else?

Other storages (FTP, Dropbox, ...) cannot hold a restic repository. django-recovery
stops with a clear error if you use one.
