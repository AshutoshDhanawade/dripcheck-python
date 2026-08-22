"""
Test settings: run the test suite against an in-memory SQLite database so the
tests do not touch the configured Supabase/PostgreSQL database.

Usage:
    python manage.py test api --settings=dripcheck_django.test_settings
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}