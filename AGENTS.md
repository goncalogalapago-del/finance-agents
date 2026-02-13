# Agent Instructions for This Repo

Follow the constitution in `CONSTITUTION.md` for all planning, coding, testing, and review decisions.

## Priority Order

When instructions conflict, apply this order:
1. Explicit user request
2. `CONSTITUTION.md`
3. Existing repository conventions
4. Default assistant behavior

## Operating Rules

1. Before implementation, restate assumptions and acceptance criteria briefly.
2. Prefer small, reviewable changes.
3. For behavior changes, add or update tests.
4. For risky changes, include rollback/mitigation notes.
5. Never introduce secrets into code or logs.
6. Use decimal-safe handling for money and UTC for internal timestamps.
7. Make error handling explicit and actionable.

## Output Expectations

1. Provide a concise change summary.
2. List what was verified (tests/checks run).
3. Call out any remaining risks or follow-ups.
