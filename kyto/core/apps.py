import os

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_tuning(sender, connection, **kwargs):
    """Wait instead of failing when the database is busy. WAL mode is opt-in (SQLITE_WAL=1) because it needs a normal local disk."""
    if connection.vendor == "sqlite":
        cur = connection.cursor()
        cur.execute("PRAGMA busy_timeout=20000;")
        if os.environ.get("SQLITE_WAL") == "1":
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        connection_created.connect(_sqlite_tuning)
