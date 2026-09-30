"""Centralized runtime configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings shared by backend services."""

    app_name: str = "Agentic RAG"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:8501"
    database_url: str = "sqlite:///./data/agentic_rag.db"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    chunk_size: int = 800
    chunk_overlap: int = 100
    chroma_persist_directory: str = "./data/chroma"
    chroma_collection_name: str = "rag_documents"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_cache_directory: str = "./data/models"
    top_k_dense: int = 10
    bm25_index_path: str = "./data/bm25/index.jsonl"
    top_k_bm25: int = 10
    top_k_hybrid: int = 10
    hybrid_rrf_k: int = 60
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k_reranked: int = 5
    max_context_items: int = 5
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 90.0
    tavily_api_key: str = ""
    serper_api_key: str = ""
    web_search_provider: str = "tavily"
    web_search_max_results: int = 5
    web_search_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so every module uses the same configuration."""
    return Settings()