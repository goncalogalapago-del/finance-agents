from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.adapters.contracts import ReadOnlyFinanceAdapter
from app.models.ingestion_run import IngestionRun, IngestionRunStatus
from app.services.audit import AuditService


class UnknownSourceError(Exception):
    pass


class IngestionService:
    def __init__(self, db: Session, adapters: dict[str, ReadOnlyFinanceAdapter]) -> None:
        self.db = db
        self.adapters = adapters
        self.audit = AuditService(db)

    def run(self, *, source: str, since_utc: Optional[datetime] = None) -> dict[str, Any]:
        adapter = self.adapters.get(source)
        if adapter is None:
            raise UnknownSourceError(f"Unknown ingestion source: {source}")

        run_id = str(uuid4())
        period_end_utc = datetime.now(timezone.utc)
        period_start_utc = since_utc or (period_end_utc - timedelta(days=30))

        self.audit.append_event(
            event_type="INGESTION_PULL_STARTED",
            entity_type="ingestion_run",
            entity_id=run_id,
            run_id=run_id,
            payload={"source": source, "period_start_utc": period_start_utc.isoformat()},
        )

        try:
            adapter.validate_read_only_scope()

            balances = list(adapter.fetch_balances(period_start_utc))
            positions = list(adapter.fetch_positions(period_start_utc))
            transactions = list(adapter.fetch_transactions(period_start_utc))

            pulled_counts = {
                "balances": len(balances),
                "positions": len(positions),
                "transactions": len(transactions),
            }

            self.db.add(
                IngestionRun(
                    id=run_id,
                    source=source,
                    status=IngestionRunStatus.SUCCESS,
                    started_at_utc=period_start_utc,
                    finished_at_utc=period_end_utc,
                    period_start_utc=period_start_utc,
                    period_end_utc=period_end_utc,
                    stats_payload=pulled_counts,
                )
            )

            self.audit.append_event(
                event_type="INGESTION_PULL_COMPLETED",
                entity_type="ingestion_run",
                entity_id=run_id,
                run_id=run_id,
                payload={"source": source, "pulled_counts": pulled_counts},
            )

            return {
                "run_id": run_id,
                "source": source,
                "status": IngestionRunStatus.SUCCESS.value,
                "pulled_counts": pulled_counts,
            }
        except Exception as exc:
            self.db.add(
                IngestionRun(
                    id=run_id,
                    source=source,
                    status=IngestionRunStatus.FAILED,
                    started_at_utc=period_start_utc,
                    finished_at_utc=datetime.now(timezone.utc),
                    period_start_utc=period_start_utc,
                    period_end_utc=period_end_utc,
                    stats_payload={"error": str(exc)},
                )
            )
            self.audit.append_event(
                event_type="INGESTION_PULL_FAILED",
                entity_type="ingestion_run",
                entity_id=run_id,
                run_id=run_id,
                payload={"source": source, "error": str(exc)},
            )
            raise
