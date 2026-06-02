from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/kora_hackathon"

    KORA_SECRET_KEY: str = ""
    KORA_PUBLIC_KEY: str = ""
    KORA_BASE_URL: str = "https://api.kora.com/v1"
    KORA_WEBHOOK_SECRET: str = ""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
