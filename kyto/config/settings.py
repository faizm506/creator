"""Kyto settings. Secure by default; relaxed only when DEBUG=True."""
import os
import sys
from pathlib import Path

from config.dburl import parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise RuntimeError("Set SECRET_KEY in the environment when DEBUG is False.")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "https://*.app.github.dev").split(",") if o.strip()
]
if _render_host:
    CSRF_TRUSTED_ORIGINS.append("https://" + _render_host)

_BAD_KEYS = ("change-me", "dev-only", "your-secret", "django-insecure")
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith(_BAD_KEYS)):
    raise RuntimeError("SECRET_KEY is missing, too short or a placeholder. Generate a real one (see README).")

SITE_NAME = os.environ.get("SITE_NAME", "Kyto")
TAGLINE = "Rise with every post."
ZYRAC_URL = "https://www.instagram.com/zyrac__/"

# Legal details shown on the Terms, Privacy and Grievance pages. Fill these in .env before you go live.
TERMS_VERSION = "2026-11-06"          # change this date whenever you change the Terms or Privacy Policy: everyone re-accepts
LEGAL_ENTITY = os.environ.get("LEGAL_ENTITY", "")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
GRIEVANCE_NAME = os.environ.get("GRIEVANCE_NAME", "")
GRIEVANCE_EMAIL = os.environ.get("GRIEVANCE_EMAIL", "")
GRIEVANCE_PHONE = os.environ.get("GRIEVANCE_PHONE", "")
GRIEVANCE_ADDRESS = os.environ.get("GRIEVANCE_ADDRESS", "")
# Paid plans ("Kyto Plus") are NOT live. Keep False until payments, GST and refund terms are set up properly.
PLUS_ENABLED = os.environ.get("PLUS_ENABLED", "False").lower() == "true"
# Paid boosting is switched off while the platform is free. Flip to True later to bring it back.
BOOST_ENABLED = os.environ.get("BOOST_ENABLED", "False").lower() == "true"
# How many reverse proxies sit in front of the app (0 in Codespaces/dev, usually 1 on Render/Railway/Nginx).
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

ADMIN_URL = os.environ.get("ADMIN_URL", "admin/")
UPI_ID = os.environ.get("UPI_ID", "yourname@upi")
UPI_NAME = os.environ.get("UPI_NAME", "Kyto")
SUPPORT_WHATSAPP = os.environ.get("SUPPORT_WHATSAPP", "")

# Boost plans: key -> (label, price in INR, days)
BOOST_PLANS = {
    "7": ("1 week", 99, 7),
    "30": ("1 month", 299, 30),
    "90": ("3 months", 699, 90),
}

# Max creators who can be Featured at once in one niche. Scarcity keeps Featured valuable and fair.
FEATURED_SLOTS_PER_NICHE = int(os.environ.get("FEATURED_SLOTS_PER_NICHE", "10"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "core.middleware.RequestId",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeaders",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.LoginRequired",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context.site",
            ]
        },
    }
]

# SQLite by default. On a host, set DATABASE_URL (for example Postgres) and nothing else changes.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": parse_database_url(os.environ["DATABASE_URL"], BASE_DIR)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3", "OPTIONS": {"timeout": 20}}}

# Cache: in memory by default (one worker). Set REDIS_URL to share rate limits and typing status between workers.
if os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.environ["REDIS_URL"]}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
try:  # keeps WhiteNoise quiet in development; collectstatic fills it for production
    STATIC_ROOT.mkdir(exist_ok=True)
except OSError:
    pass
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "settings"
LOGOUT_REDIRECT_URL = "home"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
PASSWORD_RESET_TIMEOUT = 60 * 60
DATA_UPLOAD_MAX_MEMORY_SIZE = 200_000
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# Email (password reset). Prints to the terminal by default; set SMTP values in .env to send real mail.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Kyto <no-reply@localhost>")
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_REDIRECT_EXEMPT = [r"^healthz/$", r"^readyz/$"]  # uptime checks may use plain http
SILENCED_SYSTEM_CHECKS = ["security.W021"]  # HSTS preload is a deliberate choice: we do not submit the site to the preload list
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
APP_VERSION = os.environ.get("APP_VERSION") or os.environ.get("RENDER_GIT_COMMIT", "dev")[:12]

if not DEBUG and "test" not in sys.argv:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False


# ---------------- logging, error tracking, alerts ----------------
ADMINS = [("Kyto admin", e.strip()) for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)  # 500 errors are emailed to ADMINS when this is set up
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.logging_utils.RequestIdFilter"},
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "formatters": {"std": {"format": "[%(asctime)s] %(levelname)s %(name)s rid=%(request_id)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "std", "filters": ["request_id"]},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR",
                        "filters": ["require_debug_false"], "include_html": False},
    },
    "loggers": {
        "django.request": {"handlers": ["console", "mail_admins"], "level": "WARNING", "propagate": False},
        "kyto.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "kyto.app": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:  # optional: pip install sentry-sdk. Errors then appear in Sentry with the request reference.
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()], send_default_pii=False,
                        traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0")), release=APP_VERSION)
    except ImportError:
        pass
