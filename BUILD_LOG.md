# OpsLens build log

The engineering decisions made during the build, the order they happened in, and the non-obvious choices worth flagging for anyone who picks the project up later. This is a maintenance artifact, not a setup guide; runnable steps live in the entry scripts under `scripts/`.

## Initial build

### What was built

The full project was built end to end in the order below:

1. **Skeleton + config.** `requirements.txt`, `.gitignore`, `.env.example`, `.streamlit/secrets.toml.example`, and the Pydantic settings model in `src/config.py`.
2. **Snowflake client.** Thin wrapper in `src/snowflake_client.py` with parameterized queries only and a context-managed connection lifecycle.
3. **Mock data.** Schemas in `src/mock_data/schemas.py`, generator in `src/mock_data/generate.py`. Module-scope RNG keeps the data reproducible. Anomalies injected on known days: bounce spike today, missing MC job today, HC sync failure surge yesterday, recon mismatch today.
4. **Engine.** Detectors in `src/engine/detectors.py` (z-score, failed job, missing job, threshold), reconciliation in `src/engine/reconciliation.py`, orchestration in `src/engine/pipeline.py`. Detectors are pure functions over DataFrames so they unit-test without Snowflake or LLM.
5. **LLM layer.** Abstract base in `src/llm/base.py`, three real providers (OpenAI, Anthropic, Hugging Face), deterministic template fallback in `src/llm/fallback.py`, factory that picks based on env and falls back when no key is present.
6. **Insights model + store.** `Finding` (detector output) vs `Insight` (LLM-enriched, persisted). Store reads and writes `OPS_INSIGHTS`.
7. **Security.** Sliding-window rate limiter (`LOGIN_LIMITER` 5/15min, `ACTION_LIMITER` 10/5min), Pydantic validation with allow-lists and size caps, bcrypt auth with lockout.
8. **Dashboard.** Streamlit site at `dashboard/app.py`. Login gate, overview tiles, filterable issues list, detail view, trends, rate-limited "Run analysis now" button.
9. **Email digest.** Jinja2 HTML template, SMTP send, falls back to printing the HTML if SMTP is not configured.
10. **Entry scripts.** `setup_snowflake.py`, `load_mock_data.py`, `run_analysis.py`, `send_digest.py`, `scan_secrets.py`.
11. **Tests.** 20 pytest tests covering detectors, rate limiter, and validation. All boundaries mocked so tests run with no Snowflake and no LLM.
12. **Docs.** `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `DEMO_SCRIPT.md`, `screenshots/README.md`.

### Decisions worth remembering

- **One insights table, two readers.** Email and dashboard both read `OPS_INSIGHTS`. Keeps them from drifting and means the LLM cost is paid once per run, not per page load.
- **Engine returns structured findings, not text.** Re-enrichment is just an LLM swap; no re-detection needed.
- **Deterministic fallback for LLM.** Demo never breaks when a key is missing. Template wording is good enough to look like a finished product.
- **Bcrypt directly, not through passlib.** Started on `passlib[bcrypt]`; the wrapper broke against bcrypt 5.x on Python 3.14. Switched `src/security/auth.py` to call `bcrypt.hashpw` and `bcrypt.checkpw` directly. Same primitive, fewer wrapper layers, no behavioural difference for the dashboard.
- **Lazy Snowflake import.** `src/engine/pipeline.py` and `src/insights/store.py` use `TYPE_CHECKING` for `SnowflakeClient` so the engine and the digest renderer are importable for tests and smoke runs without the Snowflake connector installed. Tests run in a few hundred milliseconds without credentials.
- **Scheduler intentionally out of the repo.** Production picks Snowflake Task, cron, or whatever orchestrator the team already trusts. Shipping one choice would imply a recommendation that may not fit the customer's stack.

### Verification

The full pipeline was exercised end to end against a Snowflake trial account:

```
setup_snowflake.py       6 tables created in OPSLENS.PUBLIC
load_mock_data.py        479 rows loaded across 5 raw tables
run_analysis.py          4 insights persisted (3 CRITICAL, 1 HIGH)
pytest                   20 / 20 passed
scan_secrets.py          clean
```

The four insights match the four anomalies the generator injects deterministically, confirming the engine wires to Snowflake correctly.

### Known operational notes

- LLM provider defaults to the deterministic fallback so the system runs end to end without an API key. Switching to OpenAI, Anthropic, or Hugging Face is a single environment variable plus a key.
- SMTP is optional. When unconfigured, the digest renders to stdout, which is useful in CI and for visual review without sending mail.
- Streamlit auth is intentionally lightweight (bcrypt plus sliding window lockout). SSO is the production move and is called out in `SECURITY.md`.

## Future work

- Snowflake Task wired to the analysis and digest stored procedures, as sketched in `ARCHITECTURE.md`, for a real 8:30 AM daily run.
- SSO via the company IdP, replacing the local bcrypt path.
- Row and column access policies on Health Cloud tables once real PHI is in play.
- Slack and Teams delivery channels behind the same `OPS_INSIGHTS` reader pattern the email digest uses today.
- An audit table that records who ran the pipeline, who signed in, and when.
