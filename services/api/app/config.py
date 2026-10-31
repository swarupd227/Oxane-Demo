from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    deal_file: Path
    llm_mode: Literal["replay", "record", "live"] = "replay"


settings = Settings()
