# Security audit

This is a proof of concept. The goal is to right-size controls to the architecture: enough to prove the team understands secure defaults, without overbuilding for a demo. This document covers the threat model, each control, the secret scan result, and residual risks with an honest list of what would change for production.

## Threat model

Assets in scope:

- Snowflake credentials (account, user, password)
- LLM API keys (OpenAI, Anthropic, Hugging Face)
- SMTP credentials
- The dashboard password
- The data in the raw and `OPS_INSIGHTS` tables (mock data in the demo, but treated as if it were real Marketing Cloud and Health Cloud exports)

Threat actors considered:

- Curious or careless internal users with dashboard access who might trigger expensive actions in a loop
- A code reviewer who would expose committed secrets if they slipped in
- A misconfigured local environment that prints credentials to logs or the frontend
- Untrusted query string or form input that tries SQL or HTML injection through the dashboard

Out of scope for the POC and called out below: network attackers, account takeover via SSO providers, sophisticated insider threats, and supply chain compromise of the LLM provider.

## Control 1: Rate limiting and lockout

**Implementation.** `src/security/rate_limiter.py` is a thread-safe sliding window limiter. It tracks attempt timestamps per key and prunes anything older than the window.

- Login lockout: 5 failed attempts in 15 minutes per username locks the account. The user sees the remaining time. A successful login resets the counter.
- Action rate limit: the "Run analysis now" button is capped at 10 runs per 5 minutes per user. This caps LLM cost if the dashboard is shared with a curious user.

**Tests.** `tests/test_rate_limiter.py` asserts lockout after 5 failures, recovery after the window, per-key isolation, that `check` does not consume an attempt, and that `reset` clears state.

## Control 2: Secret scanning

**Implementation.** `scripts/scan_secrets.py` walks the repo and matches against patterns for OpenAI keys, Anthropic keys, Hugging Face tokens, AWS access keys, bearer tokens, inline password assignments, and Snowflake account literals. Example files (`*.example`) and placeholder lines (anything containing `placeholder`, `your_`, `example`, or `REDACTED`) are intentionally skipped. The script exits non-zero on any finding and is wired into a `.pre-commit-config.yaml` along with the upstream `detect-secrets` hook for defense in depth.

**How to enable.**

```bash
pre-commit install
python scripts/scan_secrets.py
```

**Result.** Run the scan after a clean clone and you will see `Secret scan clean. Scanned N files.` No real secrets are committed; every credential lives in an environment variable.

## Control 3: Environment variables and no exposed secrets

**Implementation.**

- All credentials live in environment variables, read once in `src/config.py` through a Pydantic settings model.
- `.env.example` and `.streamlit/secrets.toml.example` ship with placeholder values only.
- `.gitignore` excludes `.env`, `.streamlit/secrets.toml`, and any local credential files.
- The Streamlit sidebar never prints secret values. It shows only the LLM provider name and the database and schema names. Logs never include credentials.
- The dashboard password is stored as a bcrypt hash (`DASHBOARD_PASSWORD_HASH`). Plaintext is never read or stored.

## Control 4: Input validation and sanitization

**Implementation.** `src/security/validation.py` defines Pydantic models for every user input:

- `IssueFilter`: caps the search string to 100 characters and a safe character class, constrains source, severity, and category to allow-lists, and bounds the date range to 90 days and to dates not in the future. `validate_range` is called after construction to enforce range invariants that depend on multiple fields.
- `RunAnalysisRequest`: rejects future dates and dates older than a year.
- `LoginRequest`: enforces username and password length and a safe username character class.

**Defense in depth.** Snowflake calls use parameterized queries only. The dashboard renders user-supplied strings into the search bar through Streamlit, which escapes by default; the HTML email template uses Jinja2 with autoescape on.

**Tests.** `tests/test_validation.py` asserts that unknown source values, oversize search strings, dangerous characters, inverted ranges, oversize ranges, future dates, and pathological username and password values are all rejected.

## Control 5: Security audit report

This document is the audit. The threat model is above; each control is implemented and tested; the secret scan is clean; the residual risks are below.

## Residual risks and assumptions

- **Streamlit auth is intentionally lightweight.** Bcrypt plus rate limiting is fit for a POC. For production we would move to SSO (Okta, Azure AD) and remove the local password path entirely.
- **Snowflake trial credentials are short-lived.** The trial expires; rotating the credential is a non-event. In production we would use Snowflake key-pair authentication with rotation.
- **No row-level or column-level access control.** Every user who can log in sees every insight. For production this is fixed with Snowflake row access policies and column masking on PHI fields, especially for the Health Cloud data.
- **No network policy.** Anyone who can reach the dashboard URL can attempt login. Production would put it behind a VPN, an IdP-aware proxy, or Snowflake network policies on top of SSO.
- **LLM data exposure.** Findings include metric names and evidence; we do not send PHI to the LLM, but operators should treat any LLM call as potentially logged by the provider. Production would either use a private deployment of the model (Bedrock, Azure OpenAI) or stay on the deterministic fallback.
- **No audit trail.** OpsLens writes insights but does not record who ran the pipeline or signed in. For production we would persist these events to Snowflake and surface them in the dashboard.
- **Single-tenant.** The schema assumes one team, one database. Multi-tenant separation would require schema-per-tenant and a tenant claim on every query.
- **Streamlit session security.** Session state is in memory and dies with the process. Sufficient for a POC; production would move auth into a real session store and use signed cookies.
