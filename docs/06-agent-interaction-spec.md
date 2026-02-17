# Agent Interaction Spec (API, CLI, Slack, Email)

## Purpose

Define how users interact in natural language with finance agents while preserving `CONSTITUTION.md` constraints:
- no real financial execution in MVP v0
- human approval required for high-impact actions
- deterministic analytics/risk/tax/proposal core
- LLM limited to narrative explanation and summarization
- full auditability

## Agent Personas

1. Ingestion Agent
- Mission: explain and trigger read-only data pulls; report freshness and source status.
- Owns: adapter health, ingestion jobs, source-level failure summaries.
- Never does: trades, transfers, account mutations.
- Example prompts:
  - "Run ingestion from Saxo and tell me what changed."
  - "Why is this month missing Lunar transactions?"

2. Portfolio Analytics Agent
- Mission: answer allocation, drift, concentration, and performance questions.
- Owns: deterministic portfolio analytics outputs.
- Example prompts:
  - "How far am I from target allocation this month?"
  - "Show my top concentration risks."

3. Risk Agent
- Mission: explain volatility proxy, drawdown, FX exposure, and stress views.
- Owns: deterministic risk metrics and guardrail explanations.
- Example prompts:
  - "What is my current drawdown vs last quarter?"
  - "How exposed am I to USD risk?"

4. Tax Agent
- Mission: explain estimated taxes (monthly/YTD), drivers, and reserve suggestions.
- Owns: deterministic tax estimator outputs.
- Example prompts:
  - "Estimate my YTD tax exposure."
  - "What caused the increase this month?"

5. Proposal Agent
- Mission: generate and explain proposals with allowlist/risk-gate checks.
- Owns: proposal creation, rationale, policy checks.
- Never does: execution; approval is explicit and separate.
- Example prompts:
  - "Propose how to reduce tech concentration."
  - "Explain why this proposal failed risk checks."

6. Macro Narrative Agent
- Mission: generate macro/geopolitical commentary mapped to deterministic exposures.
- Owns: narrative layer only.
- Example prompts:
  - "Summarize macro risks relevant to my current portfolio."
  - "Explain how rate moves could affect my exposure."

7. Reporting Agent
- Mission: compose monthly report narratives and delivery summaries.
- Owns: report sections and channel-ready formatting.
- Example prompts:
  - "Draft this month's summary in plain language."
  - "Send me a concise risk and tax recap."

8. Audit and Workflow Agent
- Mission: explain run status, approvals, and event traceability.
- Owns: run lifecycle visibility and compliance trace.
- Example prompts:
  - "Show the audit trail for this month's close."
  - "Why is this run marked DEGRADED?"

## Interaction Model

All natural language requests pass through one shared gateway:
1. Classify intent and identify target persona.
2. Execute deterministic module calls where required.
3. Use LLM only to explain and summarize outputs.
4. Return structured response + user-facing narrative.
5. Emit append-only interaction and decision audit events.

Routing rules:
- If intent is data pull/job control, route to Ingestion Agent.
- If intent is metrics/diagnostics, route to Portfolio/Risk/Tax.
- If intent is recommendation generation, route to Proposal Agent.
- If intent is macro explanation, route to Macro Narrative Agent.
- If intent is report composition/delivery status, route to Reporting Agent.
- If intent is lifecycle/compliance trace, route to Audit and Workflow Agent.

## Shared Response Contract

Every channel response should include:
- `agent`: selected persona
- `intent`: classified user intent
- `answer_text`: user-facing explanation
- `data_refs`: deterministic references used for the answer
- `actions`: optional follow-up actions (run ingestion, generate report, view proposal)
- `requires_confirmation`: true for any high-impact step
- `audit_event_ids`: IDs written to audit log

If confidence is low, return:
- `clarification_needed`: true
- `clarification_question`: single follow-up question

## API Surface (Interaction Layer)

Primary endpoint:
- `POST /agents/interactions`

Request shape (conceptual):
- `channel`: `api | cli | slack | email`
- `actor_id`: authenticated user/system identity
- `conversation_id`: thread/session correlation id
- `message`: natural language request
- `context`: optional period/account/source hints

Response shape (conceptual):
- shared response contract fields
- `interaction_id`: unique id for replay/debug

Recommended supporting endpoints:
- `GET /agents/interactions/{interaction_id}`
- `POST /agents/interactions/{interaction_id}/feedback`
- `GET /agents/personas` (discoverability/help)

Notes:
- Proposal approval/rejection remains on explicit proposal endpoints.
- Interaction endpoint never performs execution actions.

## CLI Surface

Goal: first-class terminal experience on the same interaction API.

Proposed commands:
- `finance-agents ask "How is my risk this month?"`
- `finance-agents ask --agent risk --period 2026-01 "Summarize key changes"`
- `finance-agents run ingestion --source saxo`
- `finance-agents explain proposal --id <proposal_id>`

CLI behavior:
- defaults to auto-routing by intent
- can pin persona via `--agent`
- prints both narrative output and compact structured metadata
- supports `--json` for automation-friendly output

## Slack Surface

Goal: conversational summaries and lightweight operational commands.

Inbound:
- app mention: `@finance-agents what changed this month?`
- slash command: `/fa ask ...`

Outbound:
- monthly summary messages
- run status notifications (`SUCCESS`, `DEGRADED`, `FAILED`)
- proposal summary with secure deep links for explicit approve/reject flows

Safety:
- no approval by plain Slack message text
- approval links use short-lived tokens, nonce, idempotency checks
- all interactions and button actions audited

## Email Surface

Goal: narrative delivery and asynchronous interaction.

Outbound:
- monthly report email
- degraded-mode alerts with missing data disclosures
- proposal digest emails with rationale and risk checks

Inbound (optional MVP extension):
- parse replies for questions and route through interaction gateway
- respond with explanation email and references

Safety:
- do not treat raw email text as implicit approval
- use explicit signed approval links with expiration and replay protection

## Security and Compliance Requirements

- Enforce least privilege per channel integration.
- Redact sensitive values in logs and traces.
- Validate and sanitize all user-provided text.
- Persist interaction audit events:
  - `INTERACTION_RECEIVED`
  - `INTERACTION_ROUTED`
  - `INTERACTION_RESPONDED`
  - `INTERACTION_FAILED`
- Correlate all interaction events with `conversation_id` and optional `run_id`.

## MVP Delivery Sequence

1. Implement API interaction endpoint and routing to existing modules.
2. Add CLI wrapper bound to same endpoint.
3. Add Slack inbound/outbound integration.
4. Add email outbound delivery and optional inbound parser.
5. Expand tests for intent routing, channel adapters, and audit events.

Acceptance baseline:
- same prompt yields consistent deterministic references in all channels
- no channel bypasses approval/security constraints
- every interaction is traceable in audit log
