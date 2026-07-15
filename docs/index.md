# Why django-recovery

**django-recovery** turns your Django `DATABASES` (and optionally your media directory)
into [restic](https://restic.net/) snapshots: always encrypted, deduplicated across
backups, and restorable through a management command or a superuser-only web dashboard.

You configure it like any Django storage — a backend class plus options in
`settings.py` — and get production-grade backups without writing a single shell script:

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.S3Backend",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "access_key": os.environ["AWS_KEY_ID"],
        "secret_key": os.environ["AWS_SECRET"],
        "password": os.environ["RESTIC_PASSWORD"],
    },
}
```

```bash
python manage.py recovery backup
```

## The problem with the usual approach

Most Django projects back up with some variant of `pg_dump | gzip > backup.sql.gz`
pushed to a bucket by cron. That script quietly accumulates failure modes:

- **A failed dump still uploads.** The dump crashes halfway, gzip happily compresses
  the fragment, and you discover the corruption months later — during a restore.
- **No encryption**, or hand-rolled GPG that someone must remember to configure.
- **Every backup is a full copy.** A 5 GB database uploaded nightly is ~150 GB of
  transfer and storage *per month*, even if 1% of the data changed.
- **Retention is another script.** Deleting old dumps safely is your job, forever.

## What restic brings

django-recovery delegates the hard parts to restic, a mature open-source backup engine,
and focuses on the Django side (dump commands built from `settings.DATABASES`,
management commands, the dashboard).

**Encryption is always on.** Every snapshot is encrypted (AES-256, authenticated) with
your repository password. There is no plaintext mode to forget to turn off.

**Atomic failure semantics.** Backups stream through
`restic backup --stdin-from-command`: if the database dump exits non-zero, **no snapshot
is created**. A half-written backup cannot exist.

**Deduplication.** restic splits data into content-defined chunks and stores each chunk
once. Tomorrow's backup only stores what changed since today's.

**Any storage.** Local disk, S3 and every S3-compatible service, Google Cloud Storage,
Azure Blob, SFTP — plus anything else through rclone.

## Cheaper bandwidth, cheaper storage

Deduplication is not just an integrity feature — it is the single biggest lever on your
backup bill, because cloud providers charge for **stored bytes** and **transferred
bytes**, and restic minimizes both:

- **Upload only the delta.** Consecutive dumps of a mostly-static database share almost
  all their chunks. Instead of re-uploading 5 GB nightly, restic uploads roughly the
  churn — often a few dozen MB. On metered or slow links (and on providers that bill
  ingress/egress), that difference compounds every single day.
- **Store each chunk once.** Thirty daily backups of that 5 GB database are *not*
  150 GB in your bucket; they are ~5 GB plus a month of deltas. Storage grows with your
  data's change rate, not with your backup frequency.
- **Compression on top.** restic compresses chunks with zstd before upload, shrinking
  both transfer and storage again. (django-recovery deliberately streams *uncompressed*
  dumps into restic — pre-compressed data would defeat deduplication.)
- **Retention without re-uploads.** `forget --prune` drops old snapshots and reclaims
  space in place; unchanged chunks referenced by newer snapshots are untouched.

The net effect: you can afford to back up **more often** — hourly instead of nightly —
while paying less than a naive daily full-dump pipeline.

## What django-recovery adds on top

restic alone doesn't know what a Django project is. django-recovery contributes:

- **Zero-duplication configuration** — dump/restore commands are built from
  `settings.DATABASES`; credentials are never copied into a second config system.
- **Django-native setup** — a `STORAGES`-style `RECOVERY` setting with validated
  backend classes; misconfiguration fails loudly with `ImproperlyConfigured`.
- **One management command** — `recovery init|backup|restore|snapshots|remove`, with
  confirmation prompts and a tag guard that refuses to restore a snapshot into the
  wrong database.
- **A superuser-only dashboard** — snapshots, one-click backup, guarded restore/remove,
  live job logs.

!!! warning "One thing restic cannot recover"
    If you lose the repository password, you lose the backups. There is no reset and no
    backdoor. Store the password somewhere durable and separate from the repository.

## Next steps

- [Installation](installation.md) — install the package and the restic binary.
- [Quickstart](quickstart.md) — first backup in five minutes.
- [Storage backends](backends.md) — S3, GCS, Azure, SFTP, local, rclone.
