from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agent_mode: Literal["observe", "rca", "fix"] = "rca"

    llm_provider: Literal["anthropic", "openai", "gateway"] = "anthropic"
    llm_model_fast: str = "claude-sonnet-5"
    llm_model_strong: str = "claude-sonnet-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # OpenAI-compatible internal gateway (e.g. TrueFoundry) — an alternative to
    # calling Anthropic/OpenAI directly. Model name sent to the gateway is
    # "{llm_gateway_model_prefix}/{llm_gateway_model}" when a prefix is set.
    llm_gateway_url: str = ""
    llm_gateway_model: str = ""
    llm_gateway_model_prefix: str = ""
    llm_gateway_api_key: str = ""

    github_token: str = ""
    github_repo: str = ""

    slack_webhook_url: str = ""

    agent_database_url: str = "postgresql+psycopg://agent:agent@127.0.0.1:55432/agent"

    loki_url: str = "http://127.0.0.1:3100"
    tempo_url: str = "http://127.0.0.1:3200"
    prometheus_url: str = "http://127.0.0.1:9090"


settings = Settings()
