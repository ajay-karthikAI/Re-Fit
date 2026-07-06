from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    redis_url: str
    s3_bucket: str
    s3_endpoint_url: str
    aws_access_key_id: str
    aws_secret_access_key: str
    openai_api_key: str
    relevance_threshold: float = 0.45
    max_rewrites: int = 8
    llm_input_cost_per_million: float = 0.0
    llm_output_cost_per_million: float = 0.0
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        # 3200: Playwright e2e dev server (3000/3001/3100 are taken by other apps).
        "http://localhost:3200",
        "http://127.0.0.1:3200",
    ]
    cover_letter_banned_phrases: list[str] = [
        "I am writing to express",
        "fast-paced environment",
        "wear many hats",
        "passionate about the intersection of",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
