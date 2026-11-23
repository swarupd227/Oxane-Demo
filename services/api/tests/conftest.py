import os
from pathlib import Path

import pytest

from app.admin import testdb

# The tests write clients, cases, sessions and work items. They run against their own database
# (`oxane_test`, created and migrated here), never the demo's, so nothing they create shows up
# in the demo. This runs before app.config reads DATABASE_URL.
os.environ["DATABASE_URL"] = testdb.prepare(os.environ.get("DATABASE_URL"))

from app import engine_service  # noqa: E402
from app.config import settings  # noqa: E402

RECORDED_RUN = settings.pipeline_dir
RECORDED_RESPONSES = settings.llm_fixtures


@pytest.fixture(autouse=True)
def seed_view(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Tests start from the seed view, so a recorded run cannot change what they exercise."""
    monkeypatch.setattr(settings, "pipeline_dir", tmp_path / "no-run")
    engine_service.reset()
    yield
    monkeypatch.undo()
    engine_service.reset()
