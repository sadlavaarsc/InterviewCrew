"""Provider-agnostic model resolution for OpenAI-compatible LLM APIs.

This module decouples InterviewCrew from any single model vendor.
Callers use tier aliases ("default", "premium", "fallback") or concrete
model names ("deepseek-v4-flash", "qwen3.5-flash"). The resolver picks
the right API key / base_url / model name.
"""

import warnings
from typing import Dict

from interview_crew.config import settings


# Mapping from provider name to its connection config.
_PROVIDER_REGISTRY: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "api_key": settings.deepseek_api_key,
        "base_url": settings.deepseek_base_url,
    },
    "ark": {
        "api_key": settings.ark_api_key,
        "base_url": settings.ark_base_url,
    },
    "openai": {
        "api_key": settings.openai_api_key,
        "base_url": settings.openai_base_url,
    },
    "dashscope": {
        "api_key": settings.dashscope_api_key,
        "base_url": settings.dashscope_base_url,
    },
}

# Model-name prefixes -> provider.
# Order matters: longer / more specific prefixes should come first if needed.
_MODEL_PROVIDER_PREFIXES = [
    ("deepseek-", "deepseek"),
    ("qwen", "dashscope"),           # legacy Qwen
    ("doubao", "ark"),
]

# Legacy aliases that should trigger a deprecation warning.
_DEPRECATED_ALIASES = {
    settings.qwen_plus_model,
    settings.qwen_flash_model,
    settings.dashscope_model,
}


def _warn_deprecated(model_name: str) -> None:
    if model_name in _DEPRECATED_ALIASES:
        warnings.warn(
            f"Model alias '{model_name}' (Qwen/DashScope) is deprecated. "
            f"Default is now {settings.default_model} and premium is "
            f"{settings.premium_model}.",
            DeprecationWarning,
            stacklevel=4,
        )


def resolve_model_alias(model_name: str) -> str:
    """Resolve tier aliases to concrete model names.

    Supported aliases:
      - "default"  -> settings.default_model
      - "premium"  -> settings.premium_model
      - "fallback" -> settings.fallback_model (may itself be an alias)
      - legacy "qwen3.5-flash" / "qwen3.5-plus" -> kept for compatibility
    """
    if model_name == "default":
        return settings.default_model
    if model_name == "premium":
        return settings.premium_model
    if model_name == "fallback":
        # Allow fallback_model to be either a model name or a provider alias.
        fallback = settings.fallback_model
        if fallback in ("deepseek", "ark", "openai", "dashscope"):
            provider_cfg = _PROVIDER_REGISTRY.get(fallback, _PROVIDER_REGISTRY["ark"])
            return provider_cfg.get("model", settings.ark_model)
        return fallback
    return model_name


def resolve_provider(model_name: str) -> str:
    """Return the provider key for a concrete model name."""
    # Direct provider alias (rare, but allowed).
    if model_name in _PROVIDER_REGISTRY:
        return model_name

    # Prefix matching.
    for prefix, provider in _MODEL_PROVIDER_PREFIXES:
        if model_name.startswith(prefix):
            return provider

    # Legacy exact-match aliases.
    if model_name in (settings.qwen_flash_model, settings.qwen_plus_model):
        return "dashscope"

    # Ultimate fallback: Ark.
    return "ark"


def resolve_model_params(model_name: str) -> Dict[str, str]:
    """Return {model, api_key, base_url} for any supported model alias/name.

    Emits a DeprecationWarning when legacy Qwen aliases are used.
    """
    concrete_name = resolve_model_alias(model_name)
    _warn_deprecated(concrete_name)

    provider = resolve_provider(concrete_name)
    cfg = _PROVIDER_REGISTRY.get(provider, _PROVIDER_REGISTRY["ark"])

    # If the provider has a configured default model but the caller passed a
    # provider alias (e.g. "ark"), use that configured model.
    if concrete_name in _PROVIDER_REGISTRY:
        provider_default = {
            "deepseek": settings.deepseek_default_model,
            "ark": settings.ark_model,
            "openai": settings.openai_default_model or settings.default_model,
            "dashscope": settings.dashscope_model,
        }.get(concrete_name)
        if provider_default:
            concrete_name = provider_default

    return {
        "model": concrete_name,
        "api_key": cfg["api_key"],
        "base_url": cfg["base_url"],
    }


def get_default_model() -> str:
    """Return the economy-tier default model."""
    return settings.default_model


def get_premium_model() -> str:
    """Return the quality-tier premium model."""
    return settings.premium_model


def get_fallback_model() -> str:
    """Return the fallback model used when primary provider fails."""
    return resolve_model_alias("fallback")
