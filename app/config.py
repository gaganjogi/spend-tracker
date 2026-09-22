from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "./spend.db"
    # No default: fail loudly at startup if it's not set, rather than
    # silently running unauthenticated. See app/auth.py and AI_LOG.md.
    api_key: str


settings = Settings()
