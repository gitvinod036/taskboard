"""Test-only Django settings.

Used exclusively by the automated test suite (e.g.
``python manage.py test --settings=config.test_settings``).

It reuses every production setting and only overrides the database connection
so tests run against a local SQLite database. Production
(``config.settings``) is never touched.
"""

from .settings import *  # noqa: F401,F403

# SQLite for tests - no external database required.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
