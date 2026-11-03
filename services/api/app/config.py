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
    cycle_dir: Path = Path("/fixtures/cycle")
    cycle_llm_fixtures: Path = Path("/fixtures/llm-cycle")
    llm_provider: Literal["anthropic", "foundry"] = "anthropic"
    llm_mode: Literal["replay", "record", "live"] = "replay"
    # With sign-in on, identity comes from the platform and never from the request body.
    auth_required: bool = False
    analyst_users: str = ""
    approver_users: str = ""
    static_dir: Path | None = None

    def role_of(self, user: str) -> str | None:
        def listed(names: str) -> bool:
            return user.lower() in {name.strip().lower() for name in names.split(",")}

        if listed(self.approver_users):
            return "approver"
        return "analyst" if listed(self.analyst_users) else None


settings = Settings()
