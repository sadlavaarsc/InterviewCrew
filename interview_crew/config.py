from pydantic_settings import BaseSettings, SettingsConfigDict
import warnings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ============================================================
    # Primary provider: DeepSeek (default)
    # ============================================================
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_default_model: str = "deepseek-v4-flash"
    deepseek_premium_model: str = "deepseek-v4-pro"

    # ============================================================
    # Fallback provider: Ark (Volces / 火山引擎)
    # ============================================================
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "doubao-seed-2-0-mini-260215"

    # ============================================================
    # Generic OpenAI-compatible provider (optional third option)
    # ============================================================
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_default_model: str = ""
    openai_premium_model: str = ""

    # ============================================================
    # Legacy DashScope / Qwen (DEPRECATED, kept for compatibility)
    # ============================================================
    # These fields are kept so old .env files still work, but the
    # system no longer defaults to Qwen. New deployments should
    # prefer DeepSeek (cheaper, better long-context pricing).
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen3.5-flash"
    qwen_plus_model: str = "qwen3.5-plus"
    qwen_flash_model: str = "qwen3.5-flash"

    # ============================================================
    # Model tier aliases (resolved by LLM layer)
    # ============================================================
    # Usage in code: settings.default_model / settings.premium_model
    # instead of brand-specific names like "qwen3.5-flash".
    default_model: str = "deepseek-v4-flash"      # economy tier
    premium_model: str = "deepseek-v4-pro"        # quality tier
    fallback_model: str = "ark"                   # ultimate fallback alias

    # Budgets (tokens per round)
    budget_tech1: int = 2000
    budget_tech2: int = 4000
    budget_sysdes: int = 4000
    budget_leader: int = 3000
    budget_hr: int = 2000
    budget_scribe: int = 3000

    # Redis session persistence (optional)
    redis_url: str = ""


settings = Settings()


def _warn_if_deprecated(model_name: str) -> str:
    """Emit deprecation warning for legacy Qwen aliases.

    Returns the resolved model name unchanged.
    """
    deprecated_aliases = {
        settings.qwen_plus_model,
        settings.qwen_flash_model,
        settings.dashscope_model,
    }
    if model_name in deprecated_aliases:
        warnings.warn(
            f"Model alias '{model_name}' is deprecated. "
            f"Use settings.default_model ({settings.default_model}) "
            f"or settings.premium_model ({settings.premium_model}) instead.",
            DeprecationWarning,
            stacklevel=3,
        )
    return model_name
