from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    deal_file: Path
    deal_kit_output: Path = Path("/deal-kit/output")
    ruleset_file: Path = Path("/packages/engine/rulesets/calderwood-bramble.v1.json")
    llm_mode: Literal["replay", "record", "live"] = "replay"


settings = Settings()
