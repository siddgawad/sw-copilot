from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Groq (legacy default; daily quota applies) ──────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── NVIDIA NIM (OpenAI-compatible; set LLM_PROVIDER=nim to activate) ──
    # Hosted keys are issued through NVIDIA API Catalog / build.nvidia.com.
    nim_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_model: str = "meta/llama-3.1-70b-instruct"

    # ── Ollama (local; fallback or dev testing) ──────────────────────────────
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5-coder:7b"

    # ── Provider routing ─────────────────────────────────────────────────────
    # Primary provider: "nim" | "ollama" | "groq"
    llm_provider: str = "groq"
    # Comma-separated fallback chain tried when primary hits quota/error.
    # Example: LLM_FALLBACK_CHAIN=ollama,groq
    llm_fallback_chain: str = ""

    # ── Vector store & embeddings ────────────────────────────────────────────
    chroma_persist_dir: str     = "./chroma_db"
    chroma_collection_name: str = "engineering_standards"
    embedding_model: str        = "all-MiniLM-L6-v2"

    max_rag_results: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
