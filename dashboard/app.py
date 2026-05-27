"""OpsLens Streamlit dashboard.

Reads only from OPS_INSIGHTS and the raw tables. The engine and the
LLM live in src/; this file is presentation only. All user inputs flow
through src.security.validation, and the trigger button is rate
limited so a curious viewer cannot rerun the pipeline in a loop.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure src is importable when Streamlit is launched from any cwd.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.engine.pipeline import run_pipeline  # noqa: E402
from src.insights.store import InsightStore  # noqa: E402
from src.security.auth import authenticate  # noqa: E402
from src.security.rate_limiter import ACTION_LIMITER  # noqa: E402
from src.security.validation import IssueFilter, RunAnalysisRequest  # noqa: E402
from src.snowflake_client import SnowflakeClient  # noqa: E402

st.set_page_config(page_title="OpsLens", layout="wide", page_icon="\U0001F4CA")


# Cached resources
@st.cache_resource(show_spinner=False)
def get_client() -> SnowflakeClient:
    return SnowflakeClient()


@st.cache_data(ttl=60, show_spinner=False)
def load_insights(_client_id: str) -> pd.DataFrame:
    client = get_client()
    store = InsightStore(client)
    return store.fetch_recent(days=get_settings().history_days)


@st.cache_data(ttl=60, show_spinner=False)
def load_raw(_client_id: str, table: str, date_col: str, days: int) -> pd.DataFrame:
    client = get_client()
    start = date.today() - timedelta(days=days)
    return client.query_df(
        f"SELECT * FROM {table} WHERE {date_col} >= %s ORDER BY {date_col}",
        (start,),
    )


def _login_view() -> None:
    st.title("OpsLens")
    st.caption("AI assisted operations monitoring")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", max_chars=64)
        password = st.text_input("Password", type="password", max_chars=128)
        submitted = st.form_submit_button("Sign in")
    if submitted:
        result = authenticate(username, password)
        if result.success:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error(result.message)


def _severity_color(sev: str) -> str:
    return {
        "CRITICAL": "#b91c1c",
        "HIGH": "#dc2626",
        "MEDIUM": "#f59e0b",
        "LOW": "#10b981",
    }.get(sev, "#6b7280")


def _overview(insights: pd.DataFrame) -> None:
    settings = get_settings()
    st.subheader("Today at a glance")
    today = date.today()
    today_df = insights[pd.to_datetime(insights["RUN_DATE"]).dt.date == today] if not insights.empty else insights

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Issues detected today", len(today_df))
    c2.metric("Critical", int((today_df["SEVERITY"] == "CRITICAL").sum()) if not today_df.empty else 0)
    c3.metric("High", int((today_df["SEVERITY"] == "HIGH").sum()) if not today_df.empty else 0)
    minutes_saved = len(today_df) * settings.minutes_per_manual_issue
    c4.metric("Manual review time avoided", f"{minutes_saved} min")

    if today_df.empty:
        st.info("No insights for today yet. Run the analysis from the sidebar or load mock data.")
        return

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**By severity**")
        sev_counts = today_df["SEVERITY"].value_counts().reset_index()
        sev_counts.columns = ["Severity", "Count"]
        fig = px.bar(
            sev_counts,
            x="Severity",
            y="Count",
            color="Severity",
            color_discrete_map={s: _severity_color(s) for s in sev_counts["Severity"]},
        )
        fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with cols[1]:
        st.markdown("**By source system**")
        src_counts = today_df["SOURCE_SYSTEM"].value_counts().reset_index()
        src_counts.columns = ["Source", "Count"]
        fig = px.pie(src_counts, names="Source", values="Count", hole=0.5)
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)


def _issues_list(insights: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Issues")
    if insights.empty:
        st.info("No insights yet.")
        return insights

    available_dates = pd.to_datetime(insights["RUN_DATE"]).dt.date
    default_end = available_dates.max()
    default_start = max(default_end - timedelta(days=14), available_dates.min())

    with st.expander("Filters", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            sources = st.multiselect(
                "Source",
                options=["MARKETING_CLOUD", "HEALTH_CLOUD"],
                default=[],
            )
        with c2:
            severities = st.multiselect(
                "Severity",
                options=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                default=[],
            )
        with c3:
            categories = st.multiselect(
                "Category",
                options=["ANOMALY", "FAILED_JOB", "MISSING_JOB", "RECONCILIATION", "THRESHOLD"],
                default=[],
            )

        c4, c5 = st.columns(2)
        with c4:
            date_range = st.date_input(
                "Date range",
                value=(default_start, default_end),
                min_value=available_dates.min(),
                max_value=default_end,
            )
        with c5:
            search = st.text_input("Search summary (max 100 chars)", max_chars=100)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = default_start, default_end

    try:
        f = IssueFilter(
            sources=sources,
            severities=severities,
            categories=categories,
            start_date=start_d,
            end_date=end_d,
            search=search,
        ).validate_range()
    except Exception as e:
        st.error(f"Invalid filter: {e}")
        return insights

    df = insights.copy()
    df["RUN_DATE_D"] = pd.to_datetime(df["RUN_DATE"]).dt.date
    df = df[(df["RUN_DATE_D"] >= f.start_date) & (df["RUN_DATE_D"] <= f.end_date)]
    if f.sources:
        df = df[df["SOURCE_SYSTEM"].isin(f.sources)]
    if f.severities:
        df = df[df["SEVERITY"].isin(f.severities)]
    if f.categories:
        df = df[df["CATEGORY"].isin(f.categories)]
    if f.search:
        mask = df["PLAIN_ENGLISH_SUMMARY"].str.contains(f.search, case=False, na=False)
        df = df[mask]

    display = df[
        [
            "RUN_DATE",
            "SOURCE_SYSTEM",
            "CATEGORY",
            "SEVERITY",
            "METRIC_NAME",
            "PLAIN_ENGLISH_SUMMARY",
        ]
    ].rename(
        columns={
            "RUN_DATE": "Date",
            "SOURCE_SYSTEM": "Source",
            "CATEGORY": "Category",
            "SEVERITY": "Severity",
            "METRIC_NAME": "Metric",
            "PLAIN_ENGLISH_SUMMARY": "Summary",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    return df


def _detail_view(filtered: pd.DataFrame) -> None:
    st.subheader("Detail")
    if filtered.empty:
        st.info("Select filters that match at least one issue to drill in.")
        return
    options = filtered.apply(
        lambda r: f"{r['RUN_DATE']} | {r['SEVERITY']} | {r['SOURCE_SYSTEM']} | {r['METRIC_NAME']}",
        axis=1,
    ).tolist()
    choice = st.selectbox("Pick an issue", options)
    idx = options.index(choice)
    row = filtered.iloc[idx]
    sev_color = _severity_color(row["SEVERITY"])

    st.markdown(
        f"<div style='padding:8px 12px;border-left:6px solid {sev_color};"
        f"background:#f9fafb;border-radius:4px;'>"
        f"<b>{row['SEVERITY']}</b> &middot; {row['SOURCE_SYSTEM']} &middot; {row['CATEGORY']}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**Summary.** {row['PLAIN_ENGLISH_SUMMARY']}")
    st.markdown(f"**Suggested root cause.** {row['SUGGESTED_ROOT_CAUSE']}")
    c1, c2 = st.columns(2)
    c1.metric("Observed", _fmt(row["OBSERVED_VALUE"]))
    c2.metric("Expected", _fmt(row["EXPECTED_VALUE"]))
    st.markdown("**Evidence**")
    evidence = row["EVIDENCE"]
    try:
        evidence_obj = json.loads(evidence) if isinstance(evidence, str) else evidence
    except Exception:
        evidence_obj = {"raw": evidence}
    st.json(evidence_obj)


def _fmt(v: object) -> str:
    if v is None:
        return "n/a"
    try:
        fv = float(v)
        if fv.is_integer():
            return f"{int(fv):,}"
        return f"{fv:,.4f}"
    except (TypeError, ValueError):
        return str(v)


def _trends(insights: pd.DataFrame) -> None:
    st.subheader("Trends")
    days = 30
    try:
        sends = load_raw("v1", "MC_EMAIL_SENDS", "SEND_DATE", days)
        syncs = load_raw("v1", "HC_RECORD_SYNCS", "SYNC_DATE", days)
    except Exception as e:
        st.warning(f"Could not load raw data for trends: {e}")
        return

    anomaly_dates = set()
    if not insights.empty:
        anomaly_dates = set(pd.to_datetime(insights["RUN_DATE"]).dt.date.tolist())

    tab1, tab2 = st.tabs(["Marketing Cloud bounce rate", "Health Cloud sync failures"])
    with tab1:
        if sends.empty:
            st.info("No Marketing Cloud sends loaded.")
        else:
            sends["SEND_DATE"] = pd.to_datetime(sends["SEND_DATE"]).dt.date
            agg = sends.groupby("SEND_DATE").apply(
                lambda g: pd.Series(
                    {
                        "BOUNCE_RATE": g["BOUNCED"].sum() / max(g["AUDIENCE_SIZE"].sum(), 1),
                        "BOUNCED": g["BOUNCED"].sum(),
                    }
                )
            ).reset_index()
            fig = px.line(agg, x="SEND_DATE", y="BOUNCE_RATE", markers=True, title="Daily bounce rate")
            for d in anomaly_dates:
                fig.add_vline(x=d, line_dash="dash", line_color="#dc2626", opacity=0.4)
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, use_container_width=True)
    with tab2:
        if syncs.empty:
            st.info("No Health Cloud syncs loaded.")
        else:
            syncs["SYNC_DATE"] = pd.to_datetime(syncs["SYNC_DATE"]).dt.date
            agg = syncs.groupby("SYNC_DATE")["RECORDS_FAILED"].sum().reset_index()
            fig = px.bar(agg, x="SYNC_DATE", y="RECORDS_FAILED", title="Daily Health Cloud sync failures")
            for d in anomaly_dates:
                fig.add_vline(x=d, line_dash="dash", line_color="#dc2626", opacity=0.4)
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, use_container_width=True)


def _run_now_button() -> None:
    st.markdown("---")
    st.markdown("**Run analysis now**")
    st.caption("Re-runs detection on today's data and refreshes OPS_INSIGHTS.")
    if st.button("Run analysis"):
        key = st.session_state.get("username", "anonymous")
        check = ACTION_LIMITER.record(f"run:{key}")
        if not check.allowed:
            st.error(
                f"Rate limit reached. Try again in {check.retry_after_seconds} seconds."
            )
            return
        try:
            req = RunAnalysisRequest(run_date=date.today())
        except Exception as e:
            st.error(f"Invalid request: {e}")
            return
        with st.spinner("Running detectors and enrichment..."):
            try:
                client = get_client()
                results = run_pipeline(client, run_date=req.run_date)
                st.success(f"Pipeline complete. {len(results)} insights persisted.")
                load_insights.clear()
                load_raw.clear()
            except Exception as e:
                st.error(f"Pipeline failed: {e}")


def _sidebar() -> None:
    settings = get_settings()
    st.sidebar.title("OpsLens")
    st.sidebar.write(f"Signed in as `{st.session_state.get('username', '')}`")
    st.sidebar.caption(f"LLM provider: `{settings.llm_provider}`")
    st.sidebar.caption(f"DB: `{settings.snowflake_database}.{settings.snowflake_schema}`")
    if st.sidebar.button("Sign out"):
        for k in ("authenticated", "username"):
            st.session_state.pop(k, None)
        st.rerun()
    _run_now_button()


def main() -> None:
    if not st.session_state.get("authenticated"):
        _login_view()
        return

    _sidebar()

    try:
        insights = load_insights("v1")
    except Exception as e:
        st.error(f"Could not load insights from Snowflake: {e}")
        return

    _overview(insights)
    st.markdown("---")
    filtered = _issues_list(insights)
    st.markdown("---")
    _detail_view(filtered if not filtered.empty else insights.head(10))
    st.markdown("---")
    _trends(insights)


if __name__ == "__main__":
    main()
