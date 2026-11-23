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
    casework_dir: Path = Path("/fixtures/casework")
    casework_llm_fixtures: Path = Path("/fixtures/llm-casework")
    llm_provider: Literal["anthropic", "foundry"] = "anthropic"
    llm_mode: Literal["replay", "record", "live"] = "replay"
    # With sign-in on, identity comes from the platform and never from the request body.
    auth_required: bool = False
    analyst_users: str = ""
    approver_users: str = ""
    # The third approval level, for clients that require one.
    senior_users: str = ""
    static_dir: Path | None = None
    # New deals. Their model calls go live whenever a key is set, while the scripted scenarios
    # above stay on LLM_MODE (replay by default). Recorded calls are reused by payload hash.
    deals_llm_fixtures: Path = Path("/fixtures/llm-deals")
    deals_model: str = "claude-opus-5-5"
    demo_access_code: str = ""
    live_daily_cap_usd: float = 10.0
    max_upload_mb: int = 20
    newdeals_dir: Path = Path("/deal-kit/output/newdeals")
    anthropic_api_key: str = ""
    # Tests and the offline end-to-end run only: a deterministic stand-in for the model on the
    # generated test deals. Never set in a deployment.
    deals_stub_model: bool = False
    anthropic_foundry_api_key: str = ""
    # Settings › AI provider: a Fernet key (urlsafe base64, 32 bytes) that encrypts a key saved
    # there. Unset, nothing can be saved. LOCAL_ENV_FILE, local runs only, is the repo's .env
    # mounted into the container; saving a key also writes it there.
    settings_encryption_key: str = ""
    local_env_file: str = ""

    def deals_key_set(self) -> bool:
        key = self.anthropic_foundry_api_key if self.llm_provider == "foundry" \
            else self.anthropic_api_key
        return bool(key.strip())

    def role_of(self, user: str) -> str | None:
        def listed(names: str) -> bool:
            return user.lower() in {name.strip().lower() for name in names.split(",")}

        if listed(self.senior_users):
            return "senior"
        if listed(self.approver_users):
            return "approver"
        return "analyst" if listed(self.analyst_users) else None


settings = Settings()
