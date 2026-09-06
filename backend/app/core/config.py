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
    # Raised from 256 after a delivered breakdown was cut off mid-sentence in production
    # ("...This condition checks" — 181 words ≈ 280 tokens against a 256 cap). The system prompt
    # now asks for under 80 words, so this is headroom against truncation rather than a licence
    # to be verbose: a hint that stops mid-sentence is worse than no hint.
    VLLM_MAX_TOKENS: int = 400

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
    # Days a research event is kept before the retention sweep deletes it. The
    # participant-facing copy promises 90; 0 disables the sweep entirely, which is what the
    # test suite runs with so a test database is never mutated by a background task.
    RESEARCH_RETENTION_DAYS: int = 90
    SEED_LEARNER_PASSWORD: str = "Learner123!"
    SEED_DESIGNER_PASSWORD: str = "Designer123!"
    SEED_ADMIN_PASSWORD: str = "Admin123!"

    # --- Transactional email (verification + password reset) ---
    # When EMAIL_ENABLED is False (or no connection string is set), the email service
    # logs the link instead of sending — keeps local dev unblocked without ACS secrets.
    EMAIL_ENABLED: bool = False
    ACS_CONNECTION_STRING: str = ""  # Azure Communication Services connection string (secret)
    ACS_SENDER_ADDRESS: str = "noreply@affectlearn.tech"
    # Public base URL of the frontend — used to build verification/reset links in emails.
    # Production sets this to https://affectlearn.tech.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    # Shared secret required to self-register as a course designer. Empty disables
    # designer self-registration entirely (only seeded designers exist).
    DESIGNER_INVITE_CODE: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
