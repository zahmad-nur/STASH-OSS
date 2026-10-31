"""STASH settings. Built to run only on your own computer."""
import os
from pathlib import Path

from vault.paths import data_dir, secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = data_dir(BASE_DIR)          # your documents and database live here, never in the repo
SECRET_KEY = secret_key(DATA_DIR)      # generated on first run, never committed

DEBUG = os.environ.get("STASH_DEBUG") == "1"
STASH_DEMO = os.environ.get("STASH_DEMO") == "1"   # set by `python manage.py demo`
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]

INSTALLED_APPS = ["vault", "documents", "dashboard"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "vault.middleware.LocalOnlyMiddleware",
    "vault.middleware.SecurityHeadersMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "vault.middleware.LockMiddleware",
]

ROOT_URLCONF = "stash.urls"
WSGI_APPLICATION = "stash.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "vault.context.shell"]},
}]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "stash.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# Uploads stay in memory and are encrypted before touching disk. Django's default
# would write large uploads to a plain temp file, so it's switched off.
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.MemoryFileUploadHandler"]
STASH_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = STASH_MAX_UPLOAD_BYTES
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # form fields, e.g. a drawn signature

STASH_IDLE_SECONDS = 15 * 60   # auto-lock after 15 minutes without activity
STASH_EXTRACT_TIMEOUT = 60     # seconds a PDF may take to read before it's abandoned

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"  # "no-referrer" makes browsers send Origin: null, which CSRF rejects
X_FRAME_OPTIONS = "SAMEORIGIN"

# Logs record request paths and errors only, never document contents.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
