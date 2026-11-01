from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    deal_file: Path
    deal_kit_output: Path = Path("/deal-kit/output")
    ruleset_file: Path = Path("/packages/engine/rulesets/calderwood-bramble.v1.json")
    pipeline_dir: Path = Path("/fixtures/run")
    llm_fixtures: Path = Path("/fixtures/llm")
    llm_provider: Literal["anthropic", "foundry"] = "anthropic"
    llm_mode: Literal["replay", "record", "live"] = "replay"


settings = Settings()
