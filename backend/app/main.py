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


def _model_report() -> dict:
    """Which affect models are ACTUALLY loaded, and how the code will interpret them.

    Deploy verification exists because the failure modes here are silent. Pointing
    AFFECT_MODEL_KIND at `binary_confusion` while AFFECT_MODEL_PATH still resolves to the
    4-level engagement artifact produces confident nonsense, not an error — and the only
    previous way to notice was reading App Service logs after a learner had already been
    affected. Reporting the resolved kind next to the file that is actually on disk makes
    that mismatch a single curl.

    Deliberately NOT part of the `status` verdict: a missing facial ONNX is a documented
    degradation (the pipeline runs behavioural-only, see models/README.md), not an outage.
    Never raises — every probe is guarded so a broken artifact reports rather than 500s.
    No secrets: paths and shapes only.
    """
    import os

    report: dict = {}

    def _onnx_io(path: str) -> dict:
        """Input/output names and shapes, so a width mismatch is visible before inference."""
        try:
            import onnxruntime as ort

            sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            return {
                "inputs": [{"name": i.name, "shape": i.shape} for i in sess.get_inputs()],
                "outputs": [{"name": o.name, "shape": o.shape} for o in sess.get_outputs()],
            }
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ---- behavioural ----
    try:
        from app.services.behavioral_inference import (
            _DEFAULT_MODEL_PATH,
            BehavioralModel,
        )

        beh_path = os.getenv("BEHAVIORAL_MODEL_PATH", _DEFAULT_MODEL_PATH)
        beh: dict = {"path": beh_path, "exists": os.path.exists(beh_path)}
        if beh["exists"]:
            try:
                beh["kind"] = BehavioralModel(model_path=beh_path)._kind()
            except Exception as exc:
                beh["kind"] = f"unresolved: {type(exc).__name__}"
            beh.update(_onnx_io(beh_path))
        report["behavioral"] = beh
    except Exception as exc:
        report["behavioral"] = {"error": f"{type(exc).__name__}: {exc}"}

    # ---- facial ----
    try:
        from app.agents.affect_mapping import _model_kind

        fac_path = os.getenv("AFFECT_MODEL_PATH", "models/cnn_lstm_best.onnx")
        fac: dict = {"path": fac_path, "exists": os.path.exists(fac_path), "kind": _model_kind()}
        if fac["exists"]:
            fac.update(_onnx_io(fac_path))
        report["facial"] = fac
    except Exception as exc:
        report["facial"] = {"error": f"{type(exc).__name__}: {exc}"}

    # ---- decision-path config ----
    try:
        from app.agents.edges import (
            ADAPT_COOLDOWN_CYCLES,
            ADAPT_MIN_CONFIDENCE,
            ADAPT_MIN_CONSECUTIVE,
            ADAPT_STATES,
        )
        from app.agents.fusion import forced_mode
        from app.agents.nodes.affect_detection import fusion_drives_decision

        report["decision"] = {
            "adaptStates": list(ADAPT_STATES),
            "adaptMinConfidence": ADAPT_MIN_CONFIDENCE,
            "adaptMinConsecutive": ADAPT_MIN_CONSECUTIVE,
            "adaptCooldownCycles": ADAPT_COOLDOWN_CYCLES,
            "fusionDrivesDecision": fusion_drives_decision(),
            "forcedMode": forced_mode(),
        }
    except Exception as exc:
        report["decision"] = {"error": f"{type(exc).__name__}: {exc}"}

    return report


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

