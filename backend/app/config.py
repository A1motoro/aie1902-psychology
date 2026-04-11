from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GAD7_", env_file=".env", extra="ignore")

    database_path: str = "data/app.db"
    api_prefix: str = "/v1"
    default_model_id: str = "stub-gad7-v0"
    tau_high: float = 0.85
    tau_low: float = 0.55
    disclaimer_zh: str = (
        "本结果仅供筛查与自助参考，不能替代专业诊断。若您感到痛苦或存在自伤/伤人风险，请立即联系当地紧急服务或专业机构。"
    )

    # AI：stub = 本地占位；http = OpenAI 兼容 /v1/chat/completions（DeepSeek、OpenAI、部分国内网关等）
    ai_backend: str = "stub"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 120.0
    llm_temperature_chat: float = 0.7
    llm_temperature_extract: float = 0.2
    # 部分网关不支持 response_format；可设为 False
    llm_json_response_format: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
