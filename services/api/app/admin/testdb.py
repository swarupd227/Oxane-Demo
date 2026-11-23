"""A separate database for automated tests, so they never write into the demo's.

The API test suite (tests/conftest.py) and the end-to-end stack (docker compose's api-test
service) run against `<name>_test` on the same server: created if missing, then migrated.

    python -m app.admin.testdb     # prints the test database URL after preparing it

Only the standard library and SQLAlchemy are used here, so it runs before app.config reads
DATABASE_URL.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]


def test_url(url: str) -> str:
    """The test database beside the demo's: `oxane` becomes `oxane_test`."""
    parsed = make_url(url)
    name = parsed.database or "oxane"
    if not name.endswith("_test"):
        name = f"{name}_test"
    return parsed.set(database=name).render_as_string(hide_password=False)


def ensure(url: str) -> None:
    parsed = make_url(url)
    server = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                                 {"n": parsed.database})
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        server.dispose()


def migrate(url: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_ROOT,
                   env={**os.environ, "DATABASE_URL": url}, check=True,
                   stdout=subprocess.DEVNULL)


def prepare(url: str | None = None) -> str:
    """Create and migrate the test database; returns its URL. TEST_DATABASE_URL overrides."""
    target = os.environ.get("TEST_DATABASE_URL") or test_url(url or os.environ["DATABASE_URL"])
    if not (make_url(target).database or "").endswith("_test"):
        raise SystemExit(f"Refusing to use {make_url(target).database!r} for tests: the name "
                         "must end in _test")
    ensure(target)
    migrate(target)
    return target


if __name__ == "__main__":
    print(make_url(prepare()).render_as_string(hide_password=True))
