# How it works

## Repository location

`RECOVERY['STORAGE']` names a `STORAGES` alias. django-recovery asks Django for that
storage, reads its resolved settings, and turns them into a restic repository URL plus
credential environment variables:

| Storage | Repository URL |
|---|---|
| `FileSystemStorage` | `<location>` |
| `S3Storage` | `s3:<endpoint>/<bucket_name>[/<location>]` |
| `GoogleCloudStorage` | `gs:<bucket_name>:/<location>` |
| `AzureStorage` | `azure:<azure_container>:/<location>` |
| `SFTPStorage` | `sftp:[<user>@]<host>:<root_path>` |
| `SFTPStorage` with a port | `sftp://[<user>@]<host>:<port>/<root_path>` |

django-recovery never calls the storage's own read/write methods — restic talks to
the bucket or directory directly. See [Storage](storage.md) for the full mapping.

## Backup

For each configured alias, django-recovery asks the engine connector for a dump command
(`pg_dump …`, `mysqldump …`; SQLite streams its raw file) and hands it to restic:

```
restic --json -r <repo> backup --stdin-filename <alias>.sql \
       --tag db:<alias> [--tag <your tags>] --stdin-from-command -- <dump command…>
```

(SQLite snapshots are named `<alias>.sqlite3`: the database file itself, copied
with SQLite's online backup API.) Because restic runs the dump itself and only
snapshots its stdout:

- a **failed dump produces no snapshot** — the classic "empty dump saved as a valid
  backup" failure mode cannot happen;
- the dump **streams** into the repository — no intermediate file on disk, no temp-space
  sizing problems.

Database passwords are passed to the dump out-of-band via environment variables
(`PGPASSWORD`, `MYSQL_PWD`), never on the command line, and never appear in logs or
exception text.

## Restore

django-recovery resolves the snapshot, verifies the `db:<alias>` **tag guard**, then
streams:

```
restic dump <snapshot> <alias>.sql   |   <restore command, e.g. psql -d db …>
```

The dump bytes flow straight into the restore client's stdin. Both processes must exit
zero or the restore is reported as failed.

## Tags

Every database snapshot is tagged `db:<alias>` plus any `RECOVERY["TAGS"]`; media
snapshots are tagged `media`. Tags drive `latest` resolution and the restore guard.

## Credentials flow

Cloud credentials (`AWS_*`, `GOOGLE_*`, `AZURE_*`) are read from the
[configured storage](storage.md); the repository password comes from the
top-level `RECOVERY['PASSWORD']` / `'PASSWORD_FILE'` keys (`RESTIC_PASSWORD` /
`RESTIC_PASSWORD_FILE`). Configured values override anything
inherited from the shell, so behavior is deterministic regardless of the caller's
environment. Nothing secret ever enters argv.

## Why dumps are not pre-compressed

restic deduplicates by content-defined chunking. Compressed streams change completely
after any edit, which would destroy chunk reuse between consecutive backups — so
django-recovery streams raw SQL and lets restic compress (zstd) *after* chunking.
Result: deduplication **and** compression, instead of one or the other.
