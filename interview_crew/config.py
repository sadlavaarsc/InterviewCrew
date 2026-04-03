from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Ark (fallback)
    ark_api_key: str
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "doubao-seed-2-0-mini-260215"

    # DashScope (primary)
    dashscope_api_key: str
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen3.5-flash"

    # Aliases for new architecture
    qwen_plus_model: str = "qwen3.5-plus"
    qwen_flash_model: str = "qwen3.5-flash"

    # Budgets (tokens per round)
    budget_tech1: int = 2000
    budget_tech2: int = 4000
    budget_sysdes: int = 4000
    budget_leader: int = 3000
    budget_hr: int = 2000
    budget_scribe: int = 3000


settings = Settings()
