from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # vLLM (self-hosted fine-tuned Llama 3 8B, OpenAI-compatible API) — consumed by the
    # pedagogical strategist (Story 5.1) and content adapter (Story 5.2) agent nodes.
    VLLM_ENDPOINT: str = "http://vllm:8080"
    VLLM_MODEL: str = "affectlearn/llama-3-8b-pedagogical"
    VLLM_API_KEY: str = "not-needed"  # vLLM ignores the key; OpenAI client requires a non-empty value
    VLLM_TIMEOUT_SECONDS: float = 3.0  # NFR5/architecture line 632 — fall back to rules past this
    VLLM_MAX_TOKENS: int = 256  # strategy output is compact; cap protects the latency budget

    ENVIRONMENT: str = "development"
    EXPOSE_DEV_CREDENTIALS: bool = False

    # Comma-separated list of allowed CORS origins. Defaults to local dev hosts;
    # production sets this to the deployed frontend URL (App Service).
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Observability dashboard (Monitor)
    MONITOR_ENABLED: bool = True
    MONITOR_RING_SIZE: int = 500

    SEED_ON_STARTUP: bool = False
    SEED_LEARNER_PASSWORD: str = "Learner123!"
    SEED_DESIGNER_PASSWORD: str = "Designer123!"
    SEED_ADMIN_PASSWORD: str = "Admin123!"

    model_config = {"env_file": ".env"}


settings = Settings()
