from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    VLLM_ENDPOINT: str = "http://vllm:8080"

    model_config = {"env_file": ".env"}


settings = Settings()
