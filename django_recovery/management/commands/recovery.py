"""``manage.py recovery {init,backup,restore,snapshots,remove}``.

A single Django management command exposing every backup operation through
argparse subparsers. Each subcommand is a thin wrapper over the shared
:mod:`django_recovery.services` layer; progress strings are written to
``self.stdout`` via a ``log_callback``. Destructive operations (``restore``,
``remove``) prompt for confirmation unless ``--noinput`` is given.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_recovery import services


class Command(BaseCommand):
    help = "Backup, restore, and manage restic snapshots of your databases."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="subcommand", required=True)

        subparsers.add_parser("init", help="Initialize the restic repository.")

        backup = subparsers.add_parser("backup", help="Back up databases.")
        backup.add_argument(
            "--database",
            action="append",
            dest="databases",
            help="Limit backup to this database alias (repeatable).",
        )

        subparsers.add_parser("snapshots", help="List snapshots.")

        restore = subparsers.add_parser(
            "restore", help="Restore a database from a snapshot."
        )
        restore.add_argument(
            "--snapshot",
            required=True,
            help="Snapshot id to restore, or 'latest'.",
        )
        restore.add_argument(
            "--database",
            required=True,
            help="Database alias to restore into.",
        )
        restore.add_argument(
            "--noinput",
            action="store_true",
            help="Do not prompt for confirmation.",
        )

        remove = subparsers.add_parser("remove", help="Remove a snapshot.")
        remove.add_argument("snapshot_id", help="Snapshot id to remove.")
        remove.add_argument(
            "--noinput",
            action="store_true",
            help="Do not prompt for confirmation.",
        )

    def handle(self, *args, **opts):
        subcommand = opts.get("subcommand")
        log = lambda message: self.stdout.write(message)  # noqa: E731

        if subcommand == "init":
            services.run_init(log_callback=log)
        elif subcommand == "backup":
            summary = services.run_backup(
                databases=opts.get("databases"), log_callback=log
            )
            for target, status in summary.items():
                self.stdout.write(f"{target}: {status}")
        elif subcommand == "snapshots":
            self._snapshots(log)
        elif subcommand == "restore":
            self._restore(opts, log)
        elif subcommand == "remove":
            self._remove(opts, log)
        else:  # pragma: no cover - argparse enforces required=True
            raise CommandError(
                "No subcommand given. Use one of: "
                "init, backup, restore, snapshots, remove."
            )

    def _snapshots(self, log):
        rows = services.list_snapshots(log_callback=log)
        if not rows:
            self.stdout.write("No snapshots.")
            return
        for snap in rows:
            tags = ",".join(snap.tags)
            first_path = snap.paths[0] if snap.paths else ""
            self.stdout.write(
                f"{snap.short_id}\t{snap.time}\t{tags}\t{first_path}"
            )

    def _restore(self, opts, log):
        database = opts["database"]
        snapshot = opts["snapshot"]
        if not opts.get("noinput"):
            answer = input(
                f"This will OVERWRITE database '{database}'. "
                f"Type the alias to continue: "
            )
            if answer != database:
                self.stderr.write("Aborted.")
                raise CommandError("Restore aborted: confirmation did not match.")
        services.run_restore(
            alias=database, snapshot_id=snapshot, log_callback=log
        )

    def _remove(self, opts, log):
        snapshot_id = opts["snapshot_id"]
        if not opts.get("noinput"):
            answer = input(
                f"Permanently remove snapshot {snapshot_id}? "
                f"Type 'yes' to continue: "
            )
            if answer != "yes":
                self.stderr.write("Aborted.")
                raise CommandError("Remove aborted: not confirmed.")
        services.remove_snapshot(snapshot_id, log_callback=log)
