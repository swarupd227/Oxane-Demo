from pathlib import Path

import pytest

from app import engine_service
from app.config import settings

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
