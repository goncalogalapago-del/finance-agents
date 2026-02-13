# Domain Model and Canonical Schema (MVP)

## Design Principles

- Canonical entities separated from source-specific raw payloads.
- Monetary fields stored as fixed-point decimals.
- All timestamps stored as UTC.
- Idempotency keys for ingestion and state transitions.

## Core Tables

### `institutions`
- `id` (uuid, pk)
- `name` (text)
- `type` (enum: `BROKER`, `BANK`)
- `provider_code` (text, unique) e.g. `SAXO`, `LUNAR`
- `created_at_utc` (timestamptz)

### `accounts`
- `id` (uuid, pk)
- `institution_id` (fk institutions)
- `external_account_id` (text)
- `account_label` (text)
- `account_type` (text)
- `base_currency` (char(3))
- `is_active` (bool)
- `created_at_utc` (timestamptz)
- unique: (`institution_id`, `external_account_id`)

### `instruments`
- `id` (uuid, pk)
- `isin` (text, nullable)
- `symbol` (text, nullable)
- `name` (text)
- `asset_class` (text)
- `region` (text, nullable)
- `currency` (char(3))
- `is_allowlisted` (bool, default false)
- unique candidate: (`isin`, `symbol`)

### `balances`
- `id` (uuid, pk)
- `account_id` (fk accounts)
- `as_of_utc` (timestamptz)
- `currency` (char(3))
- `balance_amount` (numeric(20,6))
- `available_amount` (numeric(20,6), nullable)
- unique: (`account_id`, `as_of_utc`, `currency`)

### `positions`
- `id` (uuid, pk)
- `account_id` (fk accounts)
- `instrument_id` (fk instruments)
- `as_of_utc` (timestamptz)
- `quantity` (numeric(24,10))
- `avg_cost` (numeric(20,6), nullable)
- `market_price` (numeric(20,6), nullable)
- `market_value` (numeric(20,6), nullable)
- unique: (`account_id`, `instrument_id`, `as_of_utc`)

### `transactions`
- `id` (uuid, pk)
- `account_id` (fk accounts)
- `instrument_id` (fk instruments, nullable)
- `external_txn_id` (text)
- `txn_type` (enum: trade/deposit/withdrawal/fee/dividend/interest/other)
- `trade_side` (enum: buy/sell, nullable)
- `executed_at_utc` (timestamptz)
- `settled_at_utc` (timestamptz, nullable)
- `quantity` (numeric(24,10), nullable)
- `price` (numeric(20,6), nullable)
- `gross_amount` (numeric(20,6), nullable)
- `fee_amount` (numeric(20,6), nullable)
- `tax_amount` (numeric(20,6), nullable)
- `net_amount` (numeric(20,6))
- `currency` (char(3))
- `raw_category` (text, nullable)
- unique: (`account_id`, `external_txn_id`)

### `fx_rates` (optional in MVP if needed for unified base reporting)
- `id` (uuid, pk)
- `base_currency` (char(3))
- `quote_currency` (char(3))
- `as_of_utc` (timestamptz)
- `rate` (numeric(20,10))
- unique: (`base_currency`, `quote_currency`, `as_of_utc`)

## Proposal and Approval Tables

### `proposals`
- `id` (uuid, pk)
- `period_month` (date) first day of month
- `status` (enum: `PROPOSED`, `APPROVED`, `REJECTED`, `EXPIRED`)
- `proposal_payload` (jsonb) deterministic recommendation data
- `narrative_payload` (jsonb) LLM explanation
- `risk_checks_payload` (jsonb) allowlist/limits checks
- `created_by` (text)
- `created_at_utc` (timestamptz)

### `proposal_actions`
- `id` (uuid, pk)
- `proposal_id` (fk proposals)
- `action_type` (enum: `BUY`, `SELL`)
- `instrument_id` (fk instruments)
- `suggested_amount` (numeric(20,6))
- `currency` (char(3))
- `rationale` (text)

### `proposal_approvals`
- `id` (uuid, pk)
- `proposal_id` (fk proposals)
- `decision` (enum: `APPROVE`, `REJECT`)
- `actor_id` (text)
- `decided_at_utc` (timestamptz)
- `token_nonce` (text)
- `idempotency_key` (text)
- unique: (`proposal_id`, `idempotency_key`)

## Audit and Operational Tables

### `audit_events` (append-only)
- `id` (bigserial, pk)
- `event_type` (text)
- `event_time_utc` (timestamptz)
- `actor_id` (text, nullable)
- `run_id` (uuid, nullable)
- `entity_type` (text)
- `entity_id` (text)
- `payload` (jsonb)
- `prev_hash` (text, nullable)
- `event_hash` (text, nullable)

### `ingestion_runs`
- `id` (uuid, pk)
- `source` (text)
- `status` (enum: `SUCCESS`, `DEGRADED`, `FAILED`)
- `started_at_utc` (timestamptz)
- `finished_at_utc` (timestamptz, nullable)
- `period_start_utc` (timestamptz)
- `period_end_utc` (timestamptz)
- `stats_payload` (jsonb)

