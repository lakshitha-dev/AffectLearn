from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.error_handler import ErrorHandlerMiddleware
from app.api.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB connection pool, Redis connection
    yield
    # Shutdown: Close connections


app = FastAPI(
    title="AffectLearn API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ErrorHandlerMiddleware)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

