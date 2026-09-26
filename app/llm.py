from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import settings

# One factory keyed on LLM_PROVIDER — every node asks for "fast" or
# "strong," never imports a provider SDK directly. Swapping providers
# (direct Anthropic, direct OpenAI, or an internal OpenAI-compatible gateway)
# is a change to this file only.


def _gateway_model_name() -> str:
    if settings.llm_gateway_model_prefix:
        return f"{settings.llm_gateway_model_prefix}/{settings.llm_gateway_model}"
    return settings.llm_gateway_model


def get_chat_model(tier: str = "fast"):
    if settings.llm_provider == "gateway":
        return ChatOpenAI(
            model=_gateway_model_name(),
            api_key=settings.llm_gateway_api_key,
            base_url=settings.llm_gateway_url,
            max_tokens=2048,
        )

    if settings.llm_provider == "anthropic":
        model = settings.llm_model_strong if tier == "strong" else settings.llm_model_fast
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key, max_tokens=2048)

    raise NotImplementedError(f"llm_provider={settings.llm_provider!r} not wired yet")
