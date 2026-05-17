from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All LLM providers configured below are FREE.

    Free tier capacities (as of 2026):
      Gemini AI Studio   — 1M tokens/minute, 1500 requests/day on free key
      Groq Cloud         — 30k tokens/minute, daily quota
      NVIDIA NIM         — 1000 calls/month per model on free tier
      OpenRouter free    — Llama-3.x, Gemma, Qwen models with $0 cost
      Ollama (local)     — unlimited, never rate-limited, runs on your machine
      HuggingFace Inference — free serverless inference for open models

    If you have NO API keys configured, the app still works via Ollama
    (install at https://ollama.com/download and pull qwen2.5-coder:7b).
    """

    # ── Gemini (Google AI Studio free tier, 1M TPM) ─────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Groq (fast Llama hosting; generous free daily quota) ────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # ── NVIDIA NIM (OpenAI-compatible free tier) ────────────────────────────
    nim_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_model: str = "meta/llama-3.1-70b-instruct"

    # ── OpenAI-compatible custom endpoint (FREE tiers like OpenRouter,
    #     HuggingFace TGI, LM Studio, etc). Plug ANY free OpenAI-compatible
    #     host without code changes.
    #     Example: openai_compat_base_url=https://openrouter.ai/api/v1
    #              openai_compat_model=meta-llama/llama-3.3-70b-instruct:free
    openai_compat_api_key: str = ""
    openai_compat_base_url: str = ""
    openai_compat_model: str = ""

    # ── Ollama (local — the always-available, never-rate-limited fallback) ──
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5-coder:7b"

    # ── Provider routing ─────────────────────────────────────────────────────
    # Primary: "gemini" | "groq" | "nim" | "openai_compat" | "ollama"
    llm_provider: str = "gemini"
    # Comma-separated fallback chain tried when primary hits quota/error.
    # 'ollama' is always appended at the end (it never rate-limits and runs
    # locally), unless LLM_DISABLE_OLLAMA_FALLBACK=1 is set.
    llm_fallback_chain: str = "groq,nim,openai_compat,ollama"
    llm_disable_ollama_fallback: bool = False

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
