"""Turn a DATABASE_URL (the format hosting platforms give you) into a Django DATABASES entry. No extra package needed."""
from urllib.parse import parse_qs, unquote, urlparse


def parse_database_url(url, base_dir=None, conn_max_age=600):
    u = urlparse(url)
    scheme = u.scheme.lower()
    if scheme in ("postgres", "postgresql", "pgsql"):
        cfg = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(u.path.lstrip("/")),
            "USER": unquote(u.username or ""),
            "PASSWORD": unquote(u.password or ""),
            "HOST": u.hostname or "",
            "PORT": str(u.port or ""),
            "CONN_MAX_AGE": conn_max_age,
            "CONN_HEALTH_CHECKS": True,
        }
        sslmode = parse_qs(u.query).get("sslmode")
        if sslmode:
            cfg["OPTIONS"] = {"sslmode": sslmode[0]}
        return cfg
    if scheme == "sqlite":
        name = unquote(u.path[1:])  # sqlite:///db.sqlite3 is relative, sqlite:////var/db.sqlite3 is absolute
        if name and not name.startswith("/") and base_dir is not None:
            name = str(base_dir / name)
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name or ":memory:", "OPTIONS": {"timeout": 20}}
    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")
