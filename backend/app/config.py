from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Imot Insight API"
    database_url: str = "sqlite:///./imot_mvp.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    frontend_origin: str = "http://localhost:3000"
    import_delay_seconds: float = 2.0
    import_max_pages: int = 150
    import_max_listings: int = 5000
    target_city: str = "София"
    target_city_url_token: str = "grad-sofiya"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
