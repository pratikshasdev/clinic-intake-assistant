"""HTTP API for the patient app and the front desk dashboard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Settings, get_settings
from .demo_patients import DEMO_PATIENTS, as_questionnaire_response
from .extract import get_extractor
from .fhir_store import FhirError, make_store
from .questionnaire import QUESTIONNAIRE
from .service import IntakeError, IntakeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class ReviewRequest(BaseModel):
    decision: str
    reviewer: str = "Front desk"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = make_store(settings.fhir_base_url)
        app.state.service = IntakeService(store, get_extractor(settings))
        yield
        await store.aclose()

    app = FastAPI(title="Clinic intake assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def service() -> IntakeService:
        return app.state.service

    @app.exception_handler(FhirError)
    async def fhir_error(_, exc: FhirError):
        from fastapi.responses import JSONResponse

        status = 404 if exc.status == 404 else 502
        return JSONResponse({"detail": str(exc), "fhir_outcome": exc.outcome}, status_code=status)

    @app.get("/api/health")
    async def health():
        svc = service()
        return {"ok": True, "fhir_server": svc.store.base_url, "extractor": svc.extractor.name}

    @app.get("/api/questionnaire")
    async def questionnaire():
        return QUESTIONNAIRE

    @app.post("/api/intake", status_code=201)
    async def submit(questionnaire_response: dict):
        try:
            return await service().submit(questionnaire_response)
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/arrivals")
    async def arrivals(hours: int = 24):
        return await service().list_arrivals(hours=hours)

    @app.get("/api/arrivals/{encounter_id}")
    async def arrival(encounter_id: str):
        return await service().get_arrival(encounter_id)

    @app.post("/api/arrivals/{encounter_id}/approve-all")
    async def approve_all(encounter_id: str, body: ReviewRequest | None = None):
        return await service().approve_all(encounter_id, (body.reviewer if body else "Front desk"))

    @app.post("/api/items/{resource_type}/{resource_id}/review")
    async def review(resource_type: str, resource_id: str, body: ReviewRequest):
        try:
            return await service().review(resource_type, resource_id, body.decision, body.reviewer)
        except IntakeError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/demo/patients")
    async def demo_patients():
        return [{"key": k, "name": f"{v['given-name']} {v['family-name']}", "reason": v["reason"]} for k, v in DEMO_PATIENTS.items()]

    @app.post("/api/demo/patients/{key}", status_code=201)
    async def submit_demo(key: str):
        if key not in DEMO_PATIENTS:
            raise HTTPException(404, "Unknown demo patient")
        return await service().submit(as_questionnaire_response(DEMO_PATIENTS[key]))

    return app


app = create_app()
