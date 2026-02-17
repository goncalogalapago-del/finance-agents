from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import build_adapter_registry
from app.db.session import get_db_session
from app.services.agent_interaction import AgentInteractionService, InvalidPreferredAgentError
from app.services.ingestion import UnknownSourceError

router = APIRouter(prefix="/channels", tags=["channels"])


class SlackInteractionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    channel_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[str] = Field(default=None, max_length=256)  # noqa: UP045
    preferred_agent: Optional[str] = Field(default=None, max_length=64)  # noqa: UP045
    context: Optional[dict[str, Any]] = None  # noqa: UP045


class SlackInteractionResponse(BaseModel):
    interaction_id: str
    reply_text: str
    agent: str
    intent: str
    audit_event_ids: list[int]


class EmailInteractionRequest(BaseModel):
    from_email: str = Field(min_length=3, max_length=320)
    subject: Optional[str] = Field(default=None, max_length=998)  # noqa: UP045
    body: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[str] = Field(default=None, max_length=256)  # noqa: UP045
    preferred_agent: Optional[str] = Field(default=None, max_length=64)  # noqa: UP045
    context: Optional[dict[str, Any]] = None  # noqa: UP045


class EmailInteractionResponse(BaseModel):
    interaction_id: str
    reply_subject: str
    reply_body: str
    agent: str
    intent: str
    audit_event_ids: list[int]


@router.post("/slack/interactions", response_model=SlackInteractionResponse)
def slack_interaction(
    request: SlackInteractionRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> SlackInteractionResponse:
    service = AgentInteractionService(db=db, adapters=build_adapter_registry())
    try:
        response = service.handle_interaction(
            channel="slack",
            actor_id=request.user_id,
            conversation_id=request.thread_id or request.channel_id,
            message=request.text,
            context=request.context,
            preferred_agent=request.preferred_agent,
        )
        db.commit()
    except (InvalidPreferredAgentError, UnknownSourceError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="slack interaction failed") from exc

    return SlackInteractionResponse(
        interaction_id=response["interaction_id"],
        reply_text=response["answer_text"],
        agent=response["agent"],
        intent=response["intent"],
        audit_event_ids=response["audit_event_ids"],
    )


@router.post("/email/interactions", response_model=EmailInteractionResponse)
def email_interaction(
    request: EmailInteractionRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> EmailInteractionResponse:
    service = AgentInteractionService(db=db, adapters=build_adapter_registry())
    try:
        response = service.handle_interaction(
            channel="email",
            actor_id=request.from_email,
            conversation_id=request.thread_id or request.from_email,
            message=(request.subject + "\n" if request.subject else "") + request.body,
            context=request.context,
            preferred_agent=request.preferred_agent,
        )
        db.commit()
    except (InvalidPreferredAgentError, UnknownSourceError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="email interaction failed") from exc

    return EmailInteractionResponse(
        interaction_id=response["interaction_id"],
        reply_subject=f"[finance-agents] {response['intent']} response",
        reply_body=response["answer_text"],
        agent=response["agent"],
        intent=response["intent"],
        audit_event_ids=response["audit_event_ids"],
    )
