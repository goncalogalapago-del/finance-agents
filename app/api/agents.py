from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import build_adapter_registry
from app.db.session import get_db_session
from app.services.agent_interaction import (
    AgentInteractionService,
    InteractionNotFoundError,
    InvalidPreferredAgentError,
)
from app.services.ingestion import UnknownSourceError

router = APIRouter(prefix="/agents", tags=["agents"])

InteractionChannel = Literal["api", "cli", "slack", "email"]


class InteractionRequest(BaseModel):
    channel: InteractionChannel = "api"
    actor_id: Optional[str] = None  # noqa: UP045
    conversation_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4000)
    context: Optional[dict[str, Any]] = None  # noqa: UP045
    preferred_agent: Optional[str] = Field(default=None, max_length=64)  # noqa: UP045


class InteractionResponse(BaseModel):
    interaction_id: str
    agent: str
    intent: str
    answer_text: str
    data_refs: list[str]
    actions: list[dict[str, Any]]
    requires_confirmation: bool
    audit_event_ids: list[int]
    clarification_needed: bool
    clarification_question: Optional[str] = None  # noqa: UP045
    created_at_utc: str


class PersonaDescriptor(BaseModel):
    key: str
    name: str
    description: str


@router.get("/personas", response_model=list[PersonaDescriptor])
def list_personas() -> list[PersonaDescriptor]:
    return [PersonaDescriptor(**persona) for persona in AgentInteractionService.list_personas()]


@router.post("/interactions", response_model=InteractionResponse)
def create_interaction(
    request: InteractionRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> InteractionResponse:
    service = AgentInteractionService(db=db, adapters=build_adapter_registry())
    try:
        response = service.handle_interaction(
            channel=request.channel,
            actor_id=request.actor_id,
            conversation_id=request.conversation_id,
            message=request.message,
            context=request.context,
            preferred_agent=request.preferred_agent,
        )
        db.commit()
        return InteractionResponse(**response)
    except (InvalidPreferredAgentError, UnknownSourceError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="interaction failed") from exc


@router.get("/interactions/{interaction_id}", response_model=InteractionResponse)
def get_interaction(
    interaction_id: str,
    db: Annotated[Session, Depends(get_db_session)],
) -> InteractionResponse:
    service = AgentInteractionService(db=db, adapters=build_adapter_registry())
    try:
        response = service.get_interaction(interaction_id=interaction_id)
        return InteractionResponse(**response)
    except InteractionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="interaction not found") from exc
