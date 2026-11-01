"""Measure accuracy across fresh model runs, because one good recording proves little.

    python -m app.evaluate --runs 3

Each run calls the model from scratch and saves nothing the workbench reads.
A run that fails outright counts as a failed run, not as a skipped one.
"""

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app import engine_service
from app.config import settings
from app.pipeline.gateway import AnthropicClient, Gateway
from app.pipeline.run import run_pipeline
from app.scoring import scorecard
from app.session import fold

SUMMARY = settings.llm_fixtures.parent / "evaluation.json"


def one_run(number: int) -> dict[str, Any]:
    recorded = settings.pipeline_dir
    with TemporaryDirectory() as folder:
        out = Path(folder)
        settings.pipeline_dir = out
        gateway = Gateway(mode="live", fixtures=out / "unused",
                          client_factory=lambda: AnthropicClient(settings.llm_provider))
        try:
            result = run_pipeline(gateway, settings.deal_kit_output / "pack", out)
            measures = scorecard(result, fold([]))["measures"]
            return {
                "run": number, "status": "completed",
                "seconds": result["usage"]["model_seconds"],
                "measures": {m["name"]: {"value": m["value"], "details": m["details"]}
                             for m in measures},
                "queue": [item["id"] for item in result["exceptions"]],
                "low_confidence": [term["name"] for term in result["terms"]
                                   if term["confidence"] in ("low", "medium")],
            }
        except Exception as error:  # noqa: BLE001 - any failure is itself the result.
            return {"run": number, "status": "failed", "error": f"{type(error).__name__}: {error}",
                    "cost_usd": gateway.total_cost_usd()}
        finally:
            settings.pipeline_dir = recorded
            engine_service.reset()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    runs = [one_run(number) for number in range(1, parser.parse_args().runs + 1)]
    SUMMARY.write_text(json.dumps(runs, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(runs, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
