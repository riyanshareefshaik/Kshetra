"""Settings read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://kshetra:kshetra@localhost:5432/kshetra"

    gee_project: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    data_gov_api_key: str = ""
    bhashini_key: str = ""
    bhashini_user_id: str = ""

    earthdata_token: str = ""
    bhoonidhi_username: str = ""
    bhoonidhi_password: str = ""

    llm_provider_order: str = "groq,gemini,ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    groq_model: str = "openai/gpt-oss-120b"
    gemini_model: str = "gemini-flash-latest"
    whisper_model: str = "small"

    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
