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
