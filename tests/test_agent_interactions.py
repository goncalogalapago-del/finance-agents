from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.adapters.fixture import FixtureReadOnlyAdapter
from app.api.agents import InteractionRequest, create_interaction, get_interaction
from app.api.channels import (
    EmailInteractionRequest,
    SlackInteractionRequest,
    email_interaction,
    slack_interaction,
)
from app.services.agent_interaction import (
    AgentInteractionService,
    InteractionNotFoundError,
    InvalidPreferredAgentError,
)
from app.services.ingestion import UnknownSourceError


def test_list_personas_returns_expected_keys(client: TestClient) -> None:
    response = client.get("/agents/personas")

    assert response.status_code == 200
    payload = response.json()
    keys = {row["key"] for row in payload}
    assert "ingestion" in keys
    assert "risk" in keys
    assert "proposal" in keys


def test_create_interaction_routes_and_persists(client: TestClient) -> None:
    create_response = client.post(
        "/agents/interactions",
        json={
            "channel": "api",
            "actor_id": "tester",
            "conversation_id": "thread-1",
            "message": "Summarize risk for this month",
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["agent"] == "risk"
    assert created["intent"] == "risk_summary"
    assert created["clarification_needed"] is False
    assert len(created["audit_event_ids"]) == 3

    get_response = client.get(f"/agents/interactions/{created['interaction_id']}")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["interaction_id"] == created["interaction_id"]
    assert retrieved["agent"] == "risk"
    assert retrieved["intent"] == "risk_summary"


def test_create_interaction_rejects_invalid_preferred_agent(client: TestClient) -> None:
    response = client.post(
        "/agents/interactions",
        json={
            "channel": "api",
            "conversation_id": "thread-2",
            "message": "hello",
            "preferred_agent": "unknown",
        },
    )

    assert response.status_code == 400
    assert "Unknown preferred agent" in response.json()["detail"]


def test_slack_interaction_endpoint_routes_message(client: TestClient) -> None:
    response = client.post(
        "/channels/slack/interactions",
        json={
            "user_id": "U123",
            "channel_id": "C1",
            "text": "What is my tax estimate?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "tax"
    assert payload["intent"] == "tax_summary"
    assert payload["reply_text"]


def test_email_interaction_endpoint_routes_message(client: TestClient) -> None:
    response = client.post(
        "/channels/email/interactions",
        json={
            "from_email": "user@example.com",
            "subject": "Portfolio check",
            "body": "How is my allocation drift?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "portfolio"
    assert payload["intent"] == "portfolio_summary"
    assert payload["reply_body"]


class _FakeDbSession:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self._commit_error = commit_error
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_agents_get_interaction_returns_404_on_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NotFoundService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def get_interaction(self, interaction_id: str) -> dict[str, Any]:
            raise InteractionNotFoundError(interaction_id)

    monkeypatch.setattr("app.api.agents.AgentInteractionService", _NotFoundService)
    monkeypatch.setattr("app.api.agents.build_adapter_registry", lambda: {"fixture": object()})

    with pytest.raises(HTTPException, match="interaction not found") as exc_info:
        get_interaction("missing-id", db=object())  # type: ignore[arg-type]

    assert exc_info.value.status_code == 404


def test_agents_create_interaction_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadRequestService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def handle_interaction(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise InvalidPreferredAgentError("invalid agent")

    class _InternalService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def handle_interaction(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise RuntimeError("boom")

    request = InteractionRequest(conversation_id="c1", message="hello")
    monkeypatch.setattr("app.api.agents.build_adapter_registry", lambda: {"fixture": object()})

    fake_db = _FakeDbSession()
    monkeypatch.setattr("app.api.agents.AgentInteractionService", _BadRequestService)
    with pytest.raises(HTTPException, match="invalid agent") as bad_exc:
        create_interaction(request=request, db=fake_db)  # type: ignore[arg-type]
    assert bad_exc.value.status_code == 400
    assert fake_db.rollback_calls == 1

    fake_db_500 = _FakeDbSession(commit_error=RuntimeError("commit failed"))
    monkeypatch.setattr("app.api.agents.AgentInteractionService", _InternalService)
    with pytest.raises(HTTPException, match="interaction failed") as internal_exc:
        create_interaction(request=request, db=fake_db_500)  # type: ignore[arg-type]
    assert internal_exc.value.status_code == 500
    assert fake_db_500.rollback_calls == 1


def test_channels_interaction_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadRequestService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def handle_interaction(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise UnknownSourceError("unknown source")

    class _InternalService:
        def __init__(self, db: Any, adapters: dict[str, Any]) -> None:
            del db, adapters

        def handle_interaction(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise RuntimeError("boom")

    monkeypatch.setattr("app.api.channels.build_adapter_registry", lambda: {"fixture": object()})

    slack_request = SlackInteractionRequest(user_id="u1", channel_id="c1", text="risk")
    email_request = EmailInteractionRequest(from_email="a@b.com", body="risk")

    bad_db = _FakeDbSession()
    monkeypatch.setattr("app.api.channels.AgentInteractionService", _BadRequestService)
    with pytest.raises(HTTPException, match="unknown source") as slack_bad:
        slack_interaction(request=slack_request, db=bad_db)  # type: ignore[arg-type]
    assert slack_bad.value.status_code == 400
    assert bad_db.rollback_calls == 1

    bad_db_email = _FakeDbSession()
    with pytest.raises(HTTPException, match="unknown source") as email_bad:
        email_interaction(request=email_request, db=bad_db_email)  # type: ignore[arg-type]
    assert email_bad.value.status_code == 400
    assert bad_db_email.rollback_calls == 1

    internal_db = _FakeDbSession(commit_error=RuntimeError("commit failed"))
    monkeypatch.setattr("app.api.channels.AgentInteractionService", _InternalService)
    with pytest.raises(HTTPException, match="slack interaction failed") as slack_internal:
        slack_interaction(request=slack_request, db=internal_db)  # type: ignore[arg-type]
    assert slack_internal.value.status_code == 500
    assert internal_db.rollback_calls == 1

    internal_db_email = _FakeDbSession(commit_error=RuntimeError("commit failed"))
    with pytest.raises(HTTPException, match="email interaction failed") as email_internal:
        email_interaction(request=email_request, db=internal_db_email)  # type: ignore[arg-type]
    assert email_internal.value.status_code == 500
    assert internal_db_email.rollback_calls == 1


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("run ingest all sources", "run_ingestion"),
        ("please sync adapter source", "ingestion_status"),
        ("show drawdown risk", "risk_summary"),
        ("my tax reserve", "tax_summary"),
        ("proposal approval flow", "proposal_summary"),
        ("macro inflation update", "macro_summary"),
        ("send report summary", "reporting_summary"),
        ("audit trace degraded run id", "audit_trace"),
        ("portfolio allocation drift", "portfolio_summary"),
        ("hello there", "needs_clarification"),
    ],
)
def test_interaction_service_classifies_and_answers_intents(
    test_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    expected_intent: str,
) -> None:
    with test_session_factory() as session:
        service = AgentInteractionService(
            db=session,
            adapters={"fixture": FixtureReadOnlyAdapter()},
        )

        if expected_intent == "run_ingestion":
            monkeypatch.setattr(
                "app.services.agent_interaction.IngestionService.run",
                lambda self, source: {  # type: ignore[no-untyped-def]
                    "run_id": "r-1",
                    "source": source,
                    "status": "SUCCESS",
                },
            )

        payload = service.handle_interaction(
            channel="api",
            actor_id="tester",
            conversation_id="c1",
            message=message,
        )
        session.commit()

    assert payload["intent"] == expected_intent
    assert payload["agent"] in {
        "ingestion",
        "risk",
        "tax",
        "proposal",
        "macro",
        "reporting",
        "audit",
        "portfolio",
    }


def test_interaction_service_handles_failures_and_lookup_edges(
    test_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_session_factory() as session:
        service = AgentInteractionService(db=session, adapters={})

        monkeypatch.setattr(
            service,
            "_resolve_route",
            lambda message, preferred_agent: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with pytest.raises(RuntimeError, match="interaction failed"):
            service.handle_interaction(
                channel="api",
                actor_id="tester",
                conversation_id="c1",
                message="anything",
            )

        monkeypatch.setattr(
            service,
            "_resolve_route",
            lambda message, preferred_agent: ("ingestion", "run_ingestion", False),
        )
        monkeypatch.setattr(
            service,
            "_build_answer",
            lambda intent, persona_key, message: (_ for _ in ()).throw(
                UnknownSourceError("No ingestion sources configured")
            ),
        )
        with pytest.raises(UnknownSourceError, match="No ingestion sources configured"):
            service.handle_interaction(
                channel="api",
                actor_id="tester",
                conversation_id="c2",
                message="run ingest",
            )

        with pytest.raises(InteractionNotFoundError):
            service.get_interaction("missing")


def test_source_from_message_and_resolve_route_guards(test_session_factory: sessionmaker) -> None:
    with test_session_factory() as session:
        service = AgentInteractionService(
            db=session,
            adapters={
                "fixture": FixtureReadOnlyAdapter(),
                "lunar": FixtureReadOnlyAdapter(),
            },
        )

        assert service._source_from_message("run all sources now") == "all"
        assert service._source_from_message("run lunar ingestion") == "lunar"
        assert service._source_from_message("run ingestion") == "fixture"
        assert service._resolve_route(message="hi", preferred_agent=None)[0] in {
            "audit",
            "portfolio",
            "risk",
            "tax",
            "proposal",
            "macro",
            "reporting",
            "ingestion",
        }

        with pytest.raises(InvalidPreferredAgentError):
            service._resolve_route(message="hello", preferred_agent="unknown")

    with test_session_factory() as session:
        service_no_adapters = AgentInteractionService(db=session, adapters={})
        with pytest.raises(UnknownSourceError, match="No ingestion sources configured"):
            service_no_adapters._source_from_message("run ingestion")
