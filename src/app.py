from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.v1 import backtest as backtest_v1
from src.api.v1 import data as data_v1
from src.api.v1 import models as models_v1
from src.api.v1 import regime as regime_v1
from src.api.v1 import signals as signals_v1
from src.api.v1 import trading as trading_v1
from src.api.v1 import uat as uat_v1

ROOT_DIR = Path(__file__).resolve().parents[1]

_version_file = ROOT_DIR / "VERSION"
_app_version = _version_file.read_text().strip() if _version_file.exists() else "0.0.0"

app = FastAPI(
    title="Newton Server",
    version=_app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.include_router(backtest_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(data_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(models_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(regime_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(signals_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(trading_v1.router, prefix="/api/v1", tags=["v1"])
app.include_router(uat_v1.router, prefix="/api/v1", tags=["v1"])

if (ROOT_DIR / "client/dist").exists():
    app.mount(
        "/",
        StaticFiles(directory=ROOT_DIR / "client/dist", html=True),
        name="client",
    )