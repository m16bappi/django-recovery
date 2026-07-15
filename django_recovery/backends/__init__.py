"""Storage backends: turn RECOVERY['OPTIONS'] into restic repository + env."""

from .azure import AzureBackend
from .base import BaseBackend
from .gcs import GCSBackend
from .generic import GenericBackend
from .local import LocalBackend
from .s3 import S3Backend
from .sftp import SFTPBackend

__all__ = [
    "AzureBackend",
    "GCSBackend",
    "GenericBackend",
    "LocalBackend",
    "BaseBackend",
    "S3Backend",
    "SFTPBackend",
]
