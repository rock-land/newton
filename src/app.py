from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.v1 import data as data_v1
from src.api.v1 import signals as signals_v1

ROOT_DIR = Path(__file__).resolve().parents[1]

app = FastAPI(
    title="Newton Server",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.include_router(data_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(signals_v1.router, prefix="/api/v1", tags=["v1"])

if (ROOT_DIR / "client/dist").exists():
    app.mount(
        "/",
        StaticFiles(directory=ROOT_DIR / "client/dist", html=True),
        name="client",
    )