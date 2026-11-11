from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_tuning(sender, connection, **kwargs):
    """Let readers and one writer work at the same time, and wait instead of failing when the database is busy."""
    if connection.vendor == "sqlite":
        cur = connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=20000;")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        connection_created.connect(_sqlite_tuning)
