from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agent_mode: Literal["observe", "rca", "fix"] = "rca"

    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model_fast: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    github_token: str = ""
    github_repo: str = ""

    slack_webhook_url: str = ""

    agent_database_url: str = "postgresql://agent:agent@127.0.0.1:55432/agent"


settings = Settings()
