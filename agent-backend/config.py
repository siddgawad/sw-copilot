from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

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
