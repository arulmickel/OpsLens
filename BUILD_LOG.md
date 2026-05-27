# OpsLens build log

A running log of what was built, in what order, and the decisions made along the way. This is the reference doc to skim before the demo or when picking the project back up later.

## Day 1: initial build (2026-05-26)

### What was built

Full project to spec. Order followed the build plan in `OPSLENS_BUILD_SPEC.md`:

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
- **Bcrypt direct, not passlib.** Initially used `passlib[bcrypt]` per spec; it broke on bcrypt 5.x on Python 3.14. Switched `src/security/auth.py` to call `bcrypt.hashpw` / `bcrypt.checkpw` directly. Same security primitive, fewer wrapper layers.
- **Lazy Snowflake import.** `src/engine/pipeline.py` and `src/insights/store.py` use `TYPE_CHECKING` for `SnowflakeClient` so the engine and digest are importable for tests and smoke runs without `snowflake-connector-python` installed.
- **Scheduler intentionally out of the repo.** Spec calls this out: production picks Snowflake Task vs cron vs orchestrator based on their stack. We document the choice rather than ship one. Added the local Windows scheduler script for the demo only (see below).

### Setup against the real Snowflake trial

Account, user, role, and dashboard password all live in the local `.env`, which is gitignored. The trial account identifier and dashboard password are intentionally not written in this log so the file stays safe to share.

Run results:

```
python scripts/setup_snowflake.py       # 6 tables created in OPSLENS.PUBLIC
python scripts/load_mock_data.py        # 479 rows loaded across 5 tables
python scripts/run_analysis.py          # 4 insights persisted (3 CRITICAL, 1 HIGH)
streamlit run dashboard/app.py          # live on http://localhost:8501
python -m pytest tests/ -q              # 20 passed
python scripts/scan_secrets.py          # clean, 51 files scanned
```

The 4 insights match the 4 injected anomalies. Confirmed end-to-end against Snowflake.

### Screenshots captured

Saved under `screenshots/`:

- `01_overview.png`
- `02_issues_list.png`
- `03_detail.png`
- `04_trend.png`
- `05_digest.png`

### Daily scheduler for the demo (added later in the same session)

Spec says document the scheduler rather than build one. For the demo we still wanted an actual 8:30 AM run on the local machine so the story is convincing:

- `scripts/daily_run.bat`: runs `run_analysis.py` then `send_digest.py`, appends output to `logs/daily.log`.
- Registered as a Windows Scheduled Task named `OpsLens Daily Digest` via the PowerShell snippet in `README.md`.

In production this would be a Snowflake Task. The bat file and the Task Scheduler entry are explicitly the local-only path for the demo and the README is honest about that.

### Known limitations to call out in the demo

- LLM is set to `fallback` in `.env`. Switch `LLM_PROVIDER` and add a key for live text.
- SMTP is blank by default. The digest script prints the HTML to stdout when SMTP is unset, which makes for an easy screenshot.
- Streamlit auth is intentionally lightweight (bcrypt + lockout). SSO is the production move, called out in `SECURITY.md`.

## How to pick this back up later

1. `python -m venv .venv` then `.venv\Scripts\activate`, `pip install -r requirements.txt`.
2. Fill `.env` from `.env.example`. The Snowflake trial expires 30 days after signup; renew or recreate.
3. `python scripts/setup_snowflake.py` and `python scripts/load_mock_data.py` rebuild the tables.
4. `python scripts/run_analysis.py` populates today's insights.
5. `streamlit run dashboard/app.py` opens the UI; log in with the credentials in `.env`.
6. If you want the daily schedule back, run the PowerShell snippet in `README.md` once as Administrator.
