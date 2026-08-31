"""Application configuration, read once from the environment."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://harmonix:harmonix@localhost:5433/harmonix"
    )
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # Auto-seed on first boot so the app is demonstrable without manual steps.
    auto_seed: bool = os.getenv("AUTO_SEED", "true").lower() in ("1", "true", "yes")

    # Retrieval
    candidate_k: int = int(os.getenv("CANDIDATE_K", "30"))

    # Confidence at or above which two records may be linked without a human.
    #
    # A threshold sweep over the synthetic set (tests/test_pipeline.py, and
    # reproducible via the offline harness) shows pair precision stays at
    # 1.000 from 0.20 to 0.80: precision here is held by the safety layer, not
    # by this number. What the threshold actually trades is recall against how
    # much work lands in the review queue. Recall plateaus around 0.52; 0.58 is
    # chosen just above the plateau so the bar still means "the evidence
    # positively supports a merge" rather than "nothing objected".
    match_threshold: float = float(os.getenv("MATCH_THRESHOLD", "0.58"))
    # Below review_floor a pair is not even worth a reviewer's time.
    review_floor: float = float(os.getenv("REVIEW_FLOOR", "0.42"))

    db_connect_retries: int = int(os.getenv("DB_CONNECT_RETRIES", "30"))
    db_connect_delay_s: float = float(os.getenv("DB_CONNECT_DELAY_S", "2.0"))

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
