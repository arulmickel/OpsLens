# 10 minute demo script

This is the script for a live walkthrough. Times are upper bounds; the live demo runs faster if you do not stop to answer questions.

## 0:00 to 1:00. The problem and who it helps

"Every morning the ops team checks Marketing Cloud and Health Cloud, scrolls through job lists in Snowflake, and tries to spot anything that broke yesterday. That is slow and easy to miss. OpsLens detects the issues automatically, explains them in plain English, suggests a likely cause, and pushes the result to inbox and to a dashboard. The user we have in mind is a non-technical operations manager who just wants to know what changed and what to do about it."

Show this README open. Point at the architecture diagram.

## 1:00 to 2:00. The mock data and how it lands in Snowflake

"We mock the daily exports the company would already have in Snowflake. Marketing Cloud sends, jobs, Health Cloud syncs, jobs, and reconciliation counts. The generator injects four anomalies on the most recent days so the detectors have something to find: a bounce-rate spike, a missing Marketing Cloud job, a Health Cloud sync failure surge, and a reconciliation mismatch."

Run the setup and load:

```bash
python scripts/setup_snowflake.py
python scripts/load_mock_data.py
```

"Each table now has 30 days of history with the anomalies baked in."

## 2:00 to 4:00. Running the analysis live

"This is the engine. It pulls the last 30 days from Snowflake, runs every detector, enriches each finding with an LLM call, and writes the result to OPS_INSIGHTS. That table is the single source of truth: the dashboard and the digest both read from it."

```bash
python scripts/run_analysis.py
```

"You can see it found the anomalies we injected, classified them by severity, and tagged each with a category. With no LLM API key it uses a deterministic template provider so the demo never breaks; set LLM_PROVIDER and a key in `.env` to swap in OpenAI, Anthropic, or Hugging Face."

## 4:00 to 7:00. Dashboard overview and drill-in

```bash
streamlit run dashboard/app.py
```

"Sign in. The lockout works after five wrong tries; we will not demo that, but the test suite covers it."

Walk through:

- The overview tile row. "Total issues today, critical and high counts, and manual review time avoided. That last number is `issues_today * minutes_per_issue` and it is the simplest possible model of the value the team gets."
- The severity and source breakdown.
- The filterable issues list. "Source, severity, category, date range, and a search box. Every filter input is validated through Pydantic with size and character limits before any query runs."
- The detail view. Click an issue. "This is the LLM output: a one-sentence plain English summary, and a one-sentence suggested cause. The cause is clearly labeled as a suggestion, not a certainty."
- The trends tab. "Daily bounce rate and Health Cloud sync failures, with anomaly days marked."

## 7:00 to 8:00. The AI summary and root-cause quality

"The summary is the thing the operations manager actually reads. Notice it is one sentence, not a paragraph, and it tells them what changed and how badly. The root cause is intentionally cautious; it starts with 'Likely cause:' and avoids inventing specifics. The same data shape goes to the email digest, so the inbox and dashboard always say the same thing."

## 8:00 to 9:00. The email digest

```bash
python scripts/send_digest.py
```

"This renders the day's insights as a responsive HTML email grouped by severity. If SMTP is configured it sends; if not, it prints to stdout so we can show the markup. The subject line summarizes the day: count of critical and high issues."

"Scheduling: in production this runs at 8:30 every morning. The recommended landing spot is a Snowflake Task that fires the analysis and chains the digest; the SQL skeleton is in ARCHITECTURE.md. For this demo I have a local Windows Scheduled Task that runs the same two scripts at 8:30; it is for the demo, not for production. I kept the orchestrator out of the repo because the right choice depends on the team's existing stack."

## 9:00 to 10:00. Efficiency and production story including security

"The efficiency win is not the minutes saved per issue, it is consistency: the system never forgets to check reconciliation. The push-model means the team does not have to remember to look at all."

"Security is documented in SECURITY.md. Five controls: a reusable rate limiter with login lockout and action throttling, a secret scanner wired into pre-commit, env-only secrets with no plaintext password, Pydantic input validation on every surface, and an honest residual-risk list. Production hardening is called out: SSO, network policy, row and column access control, and an audit trail are all the next move."

"That is OpsLens. Decoupled engine, single insights table, two delivery channels, and a fallback that keeps the demo alive even with no API key."
