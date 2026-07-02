from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Query

from .config import settings
from .service import MicroclimateService
from .storage import ObservationStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

store = ObservationStore(settings.database_path)
service = MicroclimateService(settings, store)
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(service.fetch_all, "interval", minutes=5, id="fetch_twport_and_cwa", max_instances=1)
    scheduler.start()
    if settings.fetch_on_startup:
        await service.fetch_all()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Kaohsiung Port Microclimate API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/admin/fetch")
async def fetch_now() -> dict:
    return await service.fetch_all()


@app.get("/microclimate/current")
def current() -> dict:
    return service.current()


@app.get("/microclimate/forecast")
def forecast(minutes: int = Query(90, ge=0, le=90)) -> dict:
    return service.forecast(minutes=minutes)
