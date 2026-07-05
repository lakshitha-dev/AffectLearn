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
    worker_task = None
    try:
        from app.services.research_worker import run_worker

        worker_task = asyncio.create_task(run_worker(stop_event))
    except Exception:  # never block startup on the durability worker
        worker_task = None

    yield

    # Shutdown: stop the worker, close connections
    stop_event.set()
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
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


@app.get("/health/pipeline")
async def pipeline_health():
    """Liveness of the research data-collection pipeline (for pilot monitoring).

    Reports Redis reachability, the drain worker's heartbeat, and Postgres reachability so
    a stalled pipeline is caught during Phase A. No secrets — safe to poll. `status` is "ok"
    only when all three are healthy; poll e.g. every minute and alert on "degraded".
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
    }

