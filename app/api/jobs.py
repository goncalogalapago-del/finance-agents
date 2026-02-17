from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.registry import build_adapter_registry
from app.db.session import get_db_session
from app.services.ingestion import IngestionService, UnknownSourceError

router = APIRouter(prefix="/jobs", tags=["jobs"])


class IngestionRunRequest(BaseModel):
    source: str = "fixture"
    since_utc: Optional[datetime] = None


class IngestionRunResponse(BaseModel):
    run_id: str
    source: str
    status: str
    pulled_counts: dict[str, int]


class IngestionPreflightRequest(BaseModel):
    source: str = "all"


class IngestionPreflightSourceResult(BaseModel):
    source: str
    status: str
    error: Optional[str] = None


class IngestionPreflightResponse(BaseModel):
    status: str
    sources: list[IngestionPreflightSourceResult]


@router.post("/ingestion/run", response_model=IngestionRunResponse)
def run_ingestion_job(
    request: IngestionRunRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> IngestionRunResponse:
    service = IngestionService(db=db, adapters=build_adapter_registry())
    try:
        result = service.run(source=request.source, since_utc=request.since_utc)
        db.commit()
        return IngestionRunResponse(**result)
    except UnknownSourceError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="ingestion failed") from exc


@router.post("/ingestion/preflight", response_model=IngestionPreflightResponse)
def preflight_ingestion(request: IngestionPreflightRequest) -> IngestionPreflightResponse:
    adapters = build_adapter_registry()

    if request.source == "all":
        selected = dict(sorted(adapters.items()))
        if not selected:
            raise HTTPException(status_code=400, detail="No ingestion sources configured")
    else:
        adapter = adapters.get(request.source)
        if adapter is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown ingestion source: {request.source}",
            )
        selected = {request.source: adapter}

    results: list[IngestionPreflightSourceResult] = []
    failed_sources: list[str] = []
    for source_name, adapter in selected.items():
        try:
            adapter.validate_read_only_scope()
            results.append(IngestionPreflightSourceResult(source=source_name, status="READY"))
        except Exception as exc:  # pragma: no cover - defensive error wrapping
            failed_sources.append(source_name)
            results.append(
                IngestionPreflightSourceResult(
                    source=source_name,
                    status="FAILED",
                    error=str(exc),
                )
            )

    if not failed_sources:
        status = "READY"
    elif len(failed_sources) == len(selected):
        status = "FAILED"
    else:
        status = "DEGRADED"

    return IngestionPreflightResponse(status=status, sources=results)
