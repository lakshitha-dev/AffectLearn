import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.error_handler import ErrorHandlerMiddleware
from app.api.routes import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed pre-registered accounts (only when enabled)
    from app.core.config import settings

    if settings.SEED_ON_STARTUP:
        from app.db.seed import seed_accounts
        from app.db.session import async_session

        async with async_session() as db:
            await seed_accounts(db)

    # Start the research-event worker (Story 4.7) — best-effort; no-op if Redis is down.
    stop_event = asyncio.Event()
    background_tasks: list[asyncio.Task] = []
    try:
        from app.services.research_worker import run_worker

        background_tasks.append(asyncio.create_task(run_worker(stop_event)))
    except Exception:  # never block startup on the durability worker
        pass

    # Enforce the research-data retention limit (the 90 days the participant-facing copy
    # promises). This existed as a sentence and not as a job. Started the same way as the
    # durability worker so there is ONE place background work lives; disabled when
    # RESEARCH_RETENTION_DAYS is 0, which is how the test suite runs.
    try:
        from app.services.retention_worker import run_retention_worker

        background_tasks.append(asyncio.create_task(run_retention_worker(stop_event)))
    except Exception:  # never block startup on retention
        pass

    yield

    # Shutdown: signal the workers, then cancel whatever has not stopped on its own.
    stop_event.set()
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="AffectLearn API",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware added LAST is OUTERMOST in Starlette. CORS must wrap the error handler
# so that 500 responses it generates still carry Access-Control-Allow-Origin —
# otherwise a backend error surfaces in the browser as a misleading CORS failure.
app.add_middleware(ErrorHandlerMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _model_report() -> dict:
    """Delegates to `app.services.model_report` -- shared with the admin monitor endpoint.

    Kept as a thin wrapper so `/health/pipeline`'s response shape is unchanged and existing
    tests keep their seam. The body moved out because `monitor.py` had its own divergent copy
    with superseded model-path defaults; one implementation means the two can never disagree.
    """
    from app.services.model_report import model_report

    return model_report()


@app.get("/health/pipeline")
async def pipeline_health():
    """Liveness of the research data-collection pipeline (for pilot monitoring).

    Reports Redis reachability, the drain worker's heartbeat, and Postgres reachability so
    a stalled pipeline is caught during Phase A. No secrets — safe to poll. `status` is "ok"
    only when all three are healthy; poll e.g. every minute and alert on "degraded".

    Also reports which affect MODELS are loaded (`models`). That block is informational and
    does NOT affect `status`: a missing facial ONNX degrades the pipeline to behavioural-only
    by design rather than breaking it, so it must not page anyone.
    """
    from sqlalchemy import text as _sql_text

    from app.db.session import async_session
    from app.services import redis_service, research_worker

    redis_ok = await redis_service.ping()
    worker_age = research_worker.heartbeat_age()
    worker_ok = research_worker.is_healthy()
    try:
        async with async_session() as db:
            await db.execute(_sql_text("SELECT 1"))
        pg_ok = True
    except Exception:
        pg_ok = False

    return {
        "status": "ok" if (redis_ok and worker_ok and pg_ok) else "degraded",
        "redis": redis_ok,
        "postgres": pg_ok,
        "worker": {
            "running": worker_ok,
            "heartbeatAgeS": round(worker_age, 1) if worker_age is not None else None,
        },
        "models": _model_report(),
    }

