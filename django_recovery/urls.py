"""URL routes for the staff recovery UI.

Mounted by the project under a prefix (e.g. ``recovery/``). Uses the
``recovery`` application namespace so views can ``reverse`` each other.
"""

from django.urls import path

from . import views

app_name = "recovery"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("backup/", views.start_backup, name="start_backup"),
    path("restore/", views.start_restore, name="start_restore"),
    path("remove/", views.start_remove, name="start_remove"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("jobs/<int:pk>/status/", views.job_status, name="job_status"),
]
