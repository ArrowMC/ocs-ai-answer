from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI Model
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_temperature: float = 0.3
    ai_max_tokens: int = 500
    ai_timeout: int = 30

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 5000

    # Database
    database_path: str = "./data/questions.db"


settings = Settings()
