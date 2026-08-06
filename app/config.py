from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from .env.
    """

    OPENAI_API_KEY: str

    OPENAI_MODEL: str = "gpt-5"

    OPENAI_TEMPERATURE: float = 0.2

    OPENAI_MAX_RETRIES: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()