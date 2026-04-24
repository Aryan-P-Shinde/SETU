from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "Solution Challenge API"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Firebase / GCP
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    FIREBASE_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""

    # OpenAI (Whisper API)
    OPENAI_API_KEY: str = ""

    # Whisper
    whisper_mode: str = "local"
    whisper_model: str = "base"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()