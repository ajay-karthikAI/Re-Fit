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
    board_degraded_after: int = 3
    """Consecutive fetch failures before a source board is marked ``degraded``."""
    board_dead_after: int = 10
    """Consecutive fetch failures before a source board is marked ``dead``."""
    posting_freshness_days: int = 45
    """A posting not seen in a fetch for this many days is deactivated, even if
    its board stopped being fetched (e.g. went dead) and never expired it."""
    crossboard_dedup_threshold: float = 92.0
    """rapidfuzz token_sort_ratio (0–100) over normalized company+title above
    which two postings on different boards are linked as the same role. Set high
    on purpose: bias toward under-merging (a missed dup is a minor annoyance; a
    wrong merge hides a real distinct opening)."""
    ingest_concurrency: int = 3
    """Max source boards fetched at once. A cap, not a target — we are a guest on
    these public APIs and never fan out to every board simultaneously."""
    ingest_stagger_seconds: float = 2.0
    """Delay between launching each board's fetch, on top of the concurrency cap,
    to spread request bursts."""
    digest_hour: int = 13
    """Hour of day (UTC, 0–23) the daily digest task runs."""
    digest_lookback_hours: int = 24
    """When a saved search has never sent a digest, "new" matches are those
    computed within this many hours."""
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
