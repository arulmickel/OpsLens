# Architecture

## Data flow

```
Mock data generator (src/mock_data/generate.py)
        |
        v
Snowflake RAW tables
   MC_EMAIL_SENDS, MC_JOBS, HC_RECORD_SYNCS, HC_JOBS, HC_RECONCILIATION
        |
        v
Analysis engine (src/engine/)
   - z-score anomaly detection on daily aggregates
   - failed job detection
   - missing job detection (lookback comparison)
   - threshold breach (rate exceeds configured limit)
   - reconciliation mismatch (exported vs loaded)
        |
        v
LLM enrichment (src/llm/)
   summarize(finding) and suggest_root_cause(finding, history)
        |
        v
Snowflake OPS_INSIGHTS table
        |
        +--------------------+
        |                    |
        v                    v
  Email digest         Streamlit dashboard
  (src/email_digest/)  (dashboard/app.py)
```

## Module boundaries

- `src/config.py`: the only place env vars are read. Everything downstream takes a `Settings` instance.
- `src/snowflake_client.py`: a thin wrapper. All SQL is parameterized; nothing else in the codebase calls the connector directly.
- `src/mock_data/`: generation lives behind the same Snowflake interface so swapping mock for real exports is a one-line change.
- `src/engine/`: pure functions over pandas DataFrames. No DB calls inside detectors, which keeps them unit-testable without Snowflake or LLM access.
- `src/llm/`: abstract base plus three real providers plus a deterministic fallback. The factory hides the choice.
- `src/insights/`: the persistence model. Findings are detector output; insights are LLM-enriched findings written to the DB.
- `src/email_digest/`: HTML render plus SMTP send. Render is testable without SMTP.
- `src/security/`: rate limiter, input validation, auth. Every user-touching surface goes through this.
- `dashboard/app.py`: Streamlit, presentation only.

## Key design decisions

### Why a single insights table

Email and dashboard both read from `OPS_INSIGHTS`. If we generated text on the fly in two places, the two channels could drift: a CRITICAL insight in the dashboard might be summarized differently than the same insight in the email. Persisting the enriched text gives us one source of truth, lets us audit what was sent, and removes the cost of duplicate LLM calls.

### Why the engine is decoupled from delivery

LLM enrichment is the expensive step. If the engine ran inside the dashboard, every page load would risk re-running it; if it ran inside the digest, we could not show fresh insights on demand. Putting it in the middle keeps the cost on a schedule (or an explicit "Run analysis now" trigger) and makes future channels (Slack, Teams, a webhook) trivial.

### Why detectors return structured findings, not text

A detector should not know what the operations manager wants the wording to look like. Returning a typed `Finding` keeps the detector deterministic, easy to test against a fixed series, and decouples the LLM choice from the detection logic. Swapping providers, tuning prompts, or running a re-enrichment pass touches only one module.

### Why a deterministic fallback provider

The reviewer should be able to clone the repo and demo it without an API key. Without the fallback, missing credentials would be a hard demo failure. The template provider keeps the same interface and produces readable text, just without the nuance an LLM brings.

### Why pandas for the engine

The volumes are small (days of daily exports), Snowflake returns frames cheaply, and pandas keeps the detector signatures testable in pure Python. If this grew into millions of rows per day, the same detectors translate to Snowpark or pushdown SQL without changing their callers.

### Why bcrypt instead of plain auth

Bcrypt with a stored hash means the dashboard can be deployed by anyone without having to trust a config file with a plaintext password. Combined with the sliding window lockout, this is a sensible weight for a POC. SSO would be the production move, called out in SECURITY.md.

## Configuration model

A single `Settings` object loaded from environment variables. Defaults are safe for the deterministic fallback so the app boots even with nothing configured. Detector thresholds are part of `Settings`, which lets the team tune sensitivity without code changes.

## Failure modes

- **Snowflake unavailable.** Setup, load, run, and dashboard all surface a clear error. The Streamlit cache TTL of 60 seconds means transient outages do not pin stale results forever.
- **LLM unavailable or rate-limited.** The factory falls back to the template provider on import failure; per-call failures fall back inside `pipeline.enrich`. Either way, an insight is always written.
- **SMTP unavailable.** The digest script prints the rendered HTML to stdout so the demo can still show output.

## Scheduling in production

The right place to schedule the daily run depends on the team's existing stack. The repo ships the building blocks and one local schedule for the demo, but not a committed orchestrator.

### Snowflake Task (recommended when the company already lives in Snowflake)

A Task fires inside the warehouse, calls a stored procedure that runs the engine through an external function or a Snowpark container, and chains a second task for the email step. Skeleton:

```sql
CREATE OR REPLACE TASK OPSLENS.PUBLIC.DAILY_ANALYSIS
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = 'USING CRON 30 8 * * * America/Los_Angeles'
AS
  CALL OPSLENS.PUBLIC.RUN_ANALYSIS();

CREATE OR REPLACE TASK OPSLENS.PUBLIC.DAILY_DIGEST
  WAREHOUSE = COMPUTE_WH
  AFTER OPSLENS.PUBLIC.DAILY_ANALYSIS
AS
  CALL OPSLENS.PUBLIC.SEND_DIGEST();

ALTER TASK OPSLENS.PUBLIC.DAILY_DIGEST RESUME;
ALTER TASK OPSLENS.PUBLIC.DAILY_ANALYSIS RESUME;
```

The two stored procedures wrap the Python entrypoints (Snowpark for Python, or an external function that calls a small Lambda which runs `scripts/run_analysis.py` and `scripts/send_digest.py`).

### Cron or systemd

A box that already has Python installed runs `scripts/run_analysis.py` and `scripts/send_digest.py` at 08:30. One line in crontab.

### Windows Task Scheduler

Shipped for the demo only. See the PowerShell snippet in `README.md`. Useful when a single ops engineer demos the project on their own laptop; not what a real deployment looks like.

### Cloud orchestrators

Airflow, Prefect, Dagster, GitHub Actions, or a cloud scheduler all work. Add a single DAG or workflow that calls the same two scripts. Pick this when there is already an orchestrator the team trusts.

## What is intentionally out of scope

- A live scheduler committed to the repo: production would use a Snowflake Task or a cron runner. We document the choice rather than ship one. The Windows Task Scheduler entry is a demo aid, not the production answer.
- SSO: out of scope for a POC. Lightweight bcrypt auth is sufficient and clearly labeled as such.
- Multi-tenant separation: out of scope.
- Streaming: every input is a daily export. Real-time would be a different architecture.
