from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.schemas import AugmentRequest, AugmentResponse, HealthResponse
from api.service import LegalAugmentationService, LegalServiceNotReady

logger = logging.getLogger(__name__)

app = FastAPI(title="Legal RAG Augmentation API", version="v1")
service = LegalAugmentationService()


@app.on_event("startup")
def on_startup() -> None:
    try:
        service.startup()
    except Exception:
        logger.exception("Legal RAG startup could not fully initialize")


@app.on_event("shutdown")
def on_shutdown() -> None:
    service.shutdown()


@app.get("/health", response_model=HealthResponse)
def health() -> JSONResponse:
    payload = service.health()
    status_code = 200 if payload.get("system_ready") else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.post("/v1/augment", response_model=AugmentResponse)
def augment(payload: AugmentRequest) -> AugmentResponse:
    try:
        raw = service.augment(
            question=payload.question,
            explain_routing=payload.explain_routing,
            eval_fast_mode=payload.eval_fast_mode,
        )
        raw = dict(raw)
        raw["contract_version"] = "v1"
        return AugmentResponse.model_validate(raw)
    except LegalServiceNotReady as exc:
        raise HTTPException(status_code=503, detail="legal runtime is not ready") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail="invalid augmentation payload") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("augmentation failed")
        raise HTTPException(status_code=500, detail="augmentation failed") from exc
