"""
Settings for Posterboard, all from environment variables (see README.md).

Posterboard runs behind Caddy, which asks tinyauth to authenticate every request
and passes the signed-in user on in the ``Remote-User`` header. Django itself has
no login, sessions or admin.
"""

import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(env("POSTERBOARD_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development).")
    SECRET_KEY = "insecure-development-key"

# The public address, e.g. https://posterboard.structuralpython.com
POSTERBOARD_URL = env("POSTERBOARD_URL", "http://posterboard.localhost:8080").rstrip("/")
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()] or [
    POSTERBOARD_URL.split("://", 1)[-1].split(":")[0],
    "localhost",
    "127.0.0.1",
    "testserver",
]
CSRF_TRUSTED_ORIGINS = [POSTERBOARD_URL]
# TLS ends at bunny.net's edge; Caddy passes the original scheme on.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
CSRF_COOKIE_SECURE = POSTERBOARD_URL.startswith("https://")

# The header Caddy fills from tinyauth. Without it every request is refused,
# unless POSTERBOARD_DEV_USER names a user (local development without Caddy).
AUTH_HEADER = env("POSTERBOARD_AUTH_HEADER", "Remote-User")
DEV_USER = env("POSTERBOARD_DEV_USER")

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "posts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "posts.middleware.TrustedUserMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "posts.context_processors.connection",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "posterboard.sqlite3",
        "OPTIONS": {
            # The web server and the scheduler share the file.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-ca"
TIME_ZONE = env("POSTERBOARD_TIME_ZONE", "America/Vancouver")
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"
# Uploads larger than this stream to a temporary file instead of memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# LinkedIn app ("Share on LinkedIn" + "Sign In with LinkedIn using OpenID Connect").
LINKEDIN_CLIENT_ID = env("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = env("LINKEDIN_CLIENT_SECRET")
LINKEDIN_REDIRECT_URI = env("LINKEDIN_REDIRECT_URI", f"{POSTERBOARD_URL}/linkedin/callback/")
LINKEDIN_SCOPES = env("LINKEDIN_SCOPES", "openid profile w_member_social")
# Versioned /rest API: YYYYMM. LinkedIn supports each version for about a year.
LINKEDIN_API_VERSION = env("LINKEDIN_API_VERSION", "202510")
# Warn this many days before the 60-day LinkedIn token expires.
LINKEDIN_RENEW_WARNING_DAYS = int(env("LINKEDIN_RENEW_WARNING_DAYS", "14"))

# Fernet key for the LinkedIn token at rest; derived from SECRET_KEY when unset.
POSTERBOARD_ENCRYPTION_KEY = env("POSTERBOARD_ENCRYPTION_KEY")

# Shown on the public privacy policy (/privacy/) as the address for questions.
POSTERBOARD_CONTACT_EMAIL = env("POSTERBOARD_CONTACT_EMAIL", "connor@structuralpython.com")

# Seconds between scheduler passes.
SCHEDULER_INTERVAL = int(env("POSTERBOARD_SCHEDULER_INTERVAL", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("POSTERBOARD_LOG_LEVEL", "INFO")},
}
