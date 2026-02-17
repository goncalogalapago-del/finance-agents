from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.contracts import ReadOnlyFinanceAdapter
from app.services.audit import AuditService
from app.services.ingestion import IngestionService, UnknownSourceError

InteractionChannel = Literal["api", "cli", "slack", "email"]


@dataclass(frozen=True)
class AgentPersona:
    key: str
    name: str
    description: str


PERSONAS: tuple[AgentPersona, ...] = (
    AgentPersona(
        key="ingestion",
        name="Ingestion Agent",
        description="Handles read-only ingestion runs, freshness checks, and source status.",
    ),
    AgentPersona(
        key="portfolio",
        name="Portfolio Analytics Agent",
        description="Explains allocation, drift, concentration, and performance metrics.",
    ),
    AgentPersona(
        key="risk",
        name="Risk Agent",
        description="Explains drawdown, volatility proxies, FX exposure, and stress outputs.",
    ),
    AgentPersona(
        key="tax",
        name="Tax Agent",
        description="Explains tax estimates and their deterministic drivers.",
    ),
    AgentPersona(
        key="proposal",
        name="Proposal Agent",
        description="Builds and explains proposal logic under policy and risk gates.",
    ),
    AgentPersona(
        key="macro",
        name="Macro Narrative Agent",
        description="Provides narrative context mapped to deterministic exposure inputs.",
    ),
    AgentPersona(
        key="reporting",
        name="Reporting Agent",
        description="Composes monthly report narratives and delivery summaries.",
    ),
    AgentPersona(
        key="audit",
        name="Audit and Workflow Agent",
        description="Explains run lifecycle, event traceability, and degraded states.",
    ),
)

PERSONA_BY_KEY = {persona.key: persona for persona in PERSONAS}


class InvalidPreferredAgentError(ValueError):
    pass


class InteractionNotFoundError(LookupError):
    pass


class AgentInteractionService:
    def __init__(self, db: Session, adapters: dict[str, ReadOnlyFinanceAdapter]) -> None:
        self.db = db
        self.adapters = adapters
        self.audit = AuditService(db)

    @staticmethod
    def list_personas() -> list[dict[str, str]]:
        return [
            {
                "key": persona.key,
                "name": persona.name,
                "description": persona.description,
            }
            for persona in PERSONAS
        ]

    def handle_interaction(
        self,
        *,
        channel: InteractionChannel,
        actor_id: str | None,
        conversation_id: str,
        message: str,
        context: dict[str, Any] | None = None,
        preferred_agent: str | None = None,
    ) -> dict[str, Any]:
        interaction_id = str(uuid4())

        received_event = self.audit.append_event(
            event_type="INTERACTION_RECEIVED",
            entity_type="interaction",
            entity_id=interaction_id,
            actor_id=actor_id,
            payload={
                "channel": channel,
                "conversation_id": conversation_id,
                "message": message,
                "context": context or {},
                "preferred_agent": preferred_agent,
            },
        )

        try:
            persona_key, intent, requires_confirmation = self._resolve_route(
                message=message,
                preferred_agent=preferred_agent,
            )

            routed_event = self.audit.append_event(
                event_type="INTERACTION_ROUTED",
                entity_type="interaction",
                entity_id=interaction_id,
                actor_id=actor_id,
                payload={
                    "persona": persona_key,
                    "intent": intent,
                    "requires_confirmation": requires_confirmation,
                },
            )

            answer_text, data_refs, actions, clarification_question = self._build_answer(
                intent=intent,
                persona_key=persona_key,
                message=message,
            )
            clarification_needed = clarification_question is not None

            response_payload: dict[str, Any] = {
                "interaction_id": interaction_id,
                "agent": persona_key,
                "intent": intent,
                "answer_text": answer_text,
                "data_refs": data_refs,
                "actions": actions,
                "requires_confirmation": requires_confirmation,
                "clarification_needed": clarification_needed,
                "clarification_question": clarification_question,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            responded_event = self.audit.append_event(
                event_type="INTERACTION_RESPONDED",
                entity_type="interaction",
                entity_id=interaction_id,
                actor_id=actor_id,
                payload={"response": response_payload},
            )

            response_payload["audit_event_ids"] = [
                received_event.id,
                routed_event.id,
                responded_event.id,
            ]
            return response_payload
        except Exception as exc:
            failed_event = self.audit.append_event(
                event_type="INTERACTION_FAILED",
                entity_type="interaction",
                entity_id=interaction_id,
                actor_id=actor_id,
                payload={"error": str(exc)},
            )
            if isinstance(exc, (InvalidPreferredAgentError, UnknownSourceError)):
                raise
            raise RuntimeError(
                f"interaction failed (audit_event_id={failed_event.id})"
            ) from exc

    def get_interaction(self, interaction_id: str) -> dict[str, Any]:
        audit_model = self.audit_event_model
        rows = self.db.execute(
            select(audit_model.id, audit_model.event_type, audit_model.payload)
            .where(
                audit_model.entity_type == "interaction",
                audit_model.entity_id == interaction_id,
            )
            .order_by(audit_model.id.asc())
        ).all()

        if not rows:
            raise InteractionNotFoundError(interaction_id)

        audit_event_ids = [row.id for row in rows]
        response_payload: dict[str, Any] | None = None
        for row in rows:
            if row.event_type == "INTERACTION_RESPONDED":
                response_payload = row.payload.get("response")

        if response_payload is None:
            raise InteractionNotFoundError(interaction_id)

        response_payload["audit_event_ids"] = audit_event_ids
        return response_payload

    @property
    def audit_event_model(self) -> type[Any]:
        from app.models.audit_event import AuditEvent

        return AuditEvent

    def _resolve_route(
        self,
        *,
        message: str,
        preferred_agent: str | None,
    ) -> tuple[str, str, bool]:
        if preferred_agent is not None:
            preferred = preferred_agent.strip().lower()
            if preferred not in PERSONA_BY_KEY:
                raise InvalidPreferredAgentError(f"Unknown preferred agent: {preferred_agent}")
            intent = self._classify_intent(message=message, forced_agent=preferred)
            return preferred, intent, self._requires_confirmation(intent=intent)

        intent = self._classify_intent(message=message, forced_agent=None)
        persona_key = self._persona_for_intent(intent=intent)
        return persona_key, intent, self._requires_confirmation(intent=intent)

    def _build_answer(
        self,
        *,
        intent: str,
        persona_key: str,
        message: str,
    ) -> tuple[str, list[str], list[dict[str, Any]], str | None]:
        message_lower = message.lower()

        if intent == "run_ingestion":
            source = self._source_from_message(message_lower)
            result = IngestionService(db=self.db, adapters=self.adapters).run(source=source)
            answer_text = (
                "Ingestion run completed "
                f"with status {result['status']} for source '{result['source']}'."
            )
            return (
                answer_text,
                ["/jobs/ingestion/run", "ingestion_runs", "audit_events"],
                [
                    {
                        "type": "view_ingestion_run",
                        "run_id": result["run_id"],
                        "status": result["status"],
                    }
                ],
                None,
            )

        if intent == "ingestion_status":
            return (
                "I can run a read-only ingestion pull and summarize source freshness.",
                ["/jobs/ingestion/run", "/jobs/ingestion/preflight"],
                [{"type": "run_ingestion", "default_source": "fixture"}],
                None,
            )

        if intent == "portfolio_summary":
            return (
                (
                    "Portfolio analytics are deterministic. "
                    "Ask for allocation, drift, concentration, or performance by period."
                ),
                ["/portfolio/snapshot"],
                [{"type": "get_portfolio_snapshot", "requires_period": True}],
                None,
            )

        if intent == "risk_summary":
            return (
                (
                    "Risk analytics are deterministic. "
                    "Ask for drawdown, volatility proxy, FX exposure, or stress summary by period."
                ),
                ["/risk/summary"],
                [{"type": "get_risk_summary", "requires_period": True}],
                None,
            )

        if intent == "tax_summary":
            return (
                (
                    "Tax estimates are deterministic for the selected period. "
                    "I can explain drivers and reserve guidance."
                ),
                ["/tax/estimate"],
                [{"type": "get_tax_estimate", "requires_period": True}],
                None,
            )

        if intent == "proposal_summary":
            return (
                (
                    "I can explain proposal rationale, risk checks, and approval requirements. "
                    "Execution is out of scope in MVP v0."
                ),
                [
                    "/proposals",
                    "/proposals/{proposal_id}/approve",
                    "/proposals/{proposal_id}/reject",
                ],
                [{"type": "list_proposals", "requires_period": True}],
                None,
            )

        if intent == "macro_summary":
            return (
                "Macro commentary is narrative-only and mapped to deterministic exposure outputs.",
                ["macro_digest", "risk_summary", "portfolio_snapshot"],
                [{"type": "generate_macro_summary", "requires_period": True}],
                None,
            )

        if intent == "reporting_summary":
            return (
                (
                    "I can compose monthly report summaries and delivery status "
                    "over API, CLI, Slack, or email."
                ),
                ["reporting_composer", "report_delivery"],
                [{"type": "generate_monthly_report", "requires_period": True}],
                None,
            )

        if intent == "audit_trace":
            return (
                (
                    "I can trace interaction, ingestion, proposal, and reporting lifecycle "
                    "events from the append-only audit log."
                ),
                ["audit_events"],
                [{"type": "query_audit_events", "requires_filters": True}],
                None,
            )

        return (
            (
                f"I routed this to the {PERSONA_BY_KEY[persona_key].name}. "
                "Tell me whether you want ingestion, portfolio, risk, tax, proposals, "
                "macro, reporting, or audit details."
            ),
            ["/agents/personas"],
            [],
            (
                "Which area should I focus on: ingestion, portfolio, risk, tax, "
                "proposal, macro, reporting, or audit?"
            ),
        )

    @staticmethod
    def _classify_intent(message: str, forced_agent: str | None) -> str:
        text = message.lower()

        if forced_agent == "ingestion":
            if "run" in text and "ingest" in text:
                return "run_ingestion"
            return "ingestion_status"
        if forced_agent == "portfolio":
            return "portfolio_summary"
        if forced_agent == "risk":
            return "risk_summary"
        if forced_agent == "tax":
            return "tax_summary"
        if forced_agent == "proposal":
            return "proposal_summary"
        if forced_agent == "macro":
            return "macro_summary"
        if forced_agent == "reporting":
            return "reporting_summary"
        if forced_agent == "audit":
            return "audit_trace"

        if "run" in text and "ingest" in text:
            return "run_ingestion"
        if any(token in text for token in ("ingest", "sync", "pull", "adapter", "source")):
            return "ingestion_status"
        if any(token in text for token in ("drawdown", "volatility", "fx", "stress", "risk")):
            return "risk_summary"
        if any(token in text for token in ("tax", "reserve", "realized gains", "dividend")):
            return "tax_summary"
        if any(token in text for token in ("proposal", "approve", "reject", "allowlist")):
            return "proposal_summary"
        if any(token in text for token in ("macro", "geopolit", "rate", "inflation")):
            return "macro_summary"
        if any(token in text for token in ("report", "email", "slack", "summary")):
            return "reporting_summary"
        if any(token in text for token in ("audit", "trace", "degraded", "run id")):
            return "audit_trace"
        if any(
            token in text
            for token in ("allocation", "portfolio", "concentration", "drift", "performance")
        ):
            return "portfolio_summary"
        return "needs_clarification"

    @staticmethod
    def _persona_for_intent(intent: str) -> str:
        mapping = {
            "run_ingestion": "ingestion",
            "ingestion_status": "ingestion",
            "portfolio_summary": "portfolio",
            "risk_summary": "risk",
            "tax_summary": "tax",
            "proposal_summary": "proposal",
            "macro_summary": "macro",
            "reporting_summary": "reporting",
            "audit_trace": "audit",
            "needs_clarification": "audit",
        }
        return mapping[intent]

    @staticmethod
    def _requires_confirmation(intent: str) -> bool:
        return intent == "proposal_summary"

    def _source_from_message(self, message_lower: str) -> str:
        if " all" in message_lower or "all sources" in message_lower:
            return "all"

        for source_name in sorted(self.adapters.keys()):
            if source_name in message_lower:
                return source_name

        if "fixture" in self.adapters:
            return "fixture"

        if self.adapters:
            return sorted(self.adapters.keys())[0]

        raise UnknownSourceError("No ingestion sources configured")
