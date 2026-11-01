"""The real recorded run: its responses must replay to its saved output, with no model."""

import json

import pytest
from conftest import RECORDED_RESPONSES, RECORDED_RUN

from app.config import settings
from app.pipeline.gateway import Gateway
from app.pipeline.run import run_pipeline

saved = RECORDED_RUN / "workbench.json"
pytestmark = pytest.mark.skipif(not saved.exists(), reason="No run has been recorded")


def stored(value):
    """Compare in the form the run was saved in."""
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def no_client():
    raise AssertionError("Replay must never build a model client")


def test_replay_reproduces_the_recorded_run_with_no_client(tmp_path, monkeypatch):
    out = tmp_path / "replayed"
    monkeypatch.setattr(settings, "pipeline_dir", out)
    gateway = Gateway(mode="replay", fixtures=RECORDED_RESPONSES, client_factory=no_client)
    replayed = run_pipeline(gateway, settings.deal_kit_output / "pack", out)
    assert stored(replayed) == json.loads(saved.read_text("utf-8"))


def test_recorded_run_is_real_output_with_no_unexplained_items():
    run = json.loads(saved.read_text("utf-8"))
    assert run["seed"] is False
    assert run["usage"]["cost_usd"] > 0
    assert len(run["terms"]) == 26
    assert all(term["verified"] for term in run["terms"] if term["status"] != "missing")
    assert not [item["id"] for item in run["exceptions"] if item["id"].startswith("Q")]
