import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = (os.getenv("TRUSTAGENT_API_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")

CATEGORY_LABELS = {
    "Instagram": "instagram",
    "X (Twitter)": "x",
    "LinkedIn": "linkedin",
    "YouTube": "youtube",
    "Facebook": "facebook",
    "Telegram": "telegram",
    "Mobile App": "mobile_app",
    "Startup": "startup",
    "Freelancer": "freelancer",
    "Website": "website",
}

POLICY_CHECKS = {
    "instagram": [
        "Engagement-to-follower consistency",
        "Review spike anomaly",
        "Account age and profile completeness",
    ],
    "x": [
        "Interaction quality baseline",
        "Review/comment burst behavior",
        "Profile completion confidence",
    ],
    "linkedin": [
        "Professional profile completeness",
        "Identity maturity signal",
        "Review integrity and sentiment consistency",
    ],
    "youtube": [
        "View-to-engagement authenticity",
        "Channel maturity and continuity",
        "Comment/review spike behavior",
    ],
    "facebook": [
        "Comment/review burst detection",
        "Profile integrity quality",
        "Behavioral anomaly cross-check",
    ],
    "telegram": [
        "Channel metadata completeness",
        "Engagement consistency",
        "History longevity signal",
    ],
    "mobile_app": [
        "App-store rating confidence",
        "Permission risk mismatch",
        "Publisher maturity and brand impersonation",
    ],
    "startup": [
        "Founder/team visibility",
        "Funding-claim corroboration",
        "Traffic consistency with growth claims",
    ],
    "freelancer": [
        "Review concentration and burst checks",
        "Profile completeness and trust baseline",
        "Account maturity signal",
    ],
    "website": [
        "Domain-age trust history",
        "Engagement and sentiment coherence",
        "Review velocity anomaly checks",
    ],
}


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def follower_authenticity_breakdown(metrics):
    engagement = metrics.get("engagement_rate", 0.02)
    review_spike = metrics.get("review_spike_ratio", 0.3)
    profile_completeness = metrics.get("profile_completeness", 0.8)

    bot_score = (
        0.55 * (1 - clamp(engagement / 0.12, 0, 1))
        + 0.30 * clamp(review_spike, 0, 1)
        + 0.15 * (1 - clamp(profile_completeness, 0, 1))
    )
    likely_bot_pct = int(round(clamp(bot_score, 0.05, 0.95) * 100))
    authentic_pct = 100 - likely_bot_pct
    return likely_bot_pct, authentic_pct


def sentiment_breakdown(metrics):
    sentiment_score = clamp(metrics.get("sentiment_score", 0.6), 0, 1)
    review_spike = clamp(metrics.get("review_spike_ratio", 0.3), 0, 1)

    total = 100
    positive = int(round((0.35 + 0.6 * sentiment_score - 0.2 * review_spike) * total))
    neutral = int(round((0.2 + 0.25 * (1 - abs(sentiment_score - 0.5) * 2)) * total))
    positive = clamp(positive, 0, total)
    neutral = clamp(neutral, 0, total - positive)
    negative = total - positive - neutral
    return [negative, neutral, positive]


def post_json(path, payload):
    headers = {}
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=30, headers=headers)
    response.raise_for_status()
    return response.json()


def get_json(path, params=None):
    headers = {}
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=30, headers=headers)
    response.raise_for_status()
    return response.json()


def get_history(target=None, category=None, limit=20):
    params = {"limit": limit}
    if target:
        params["target"] = target
    if category:
        params["category"] = category
    return get_json("/history", params=params)


def get_analytics(limit=10):
    return get_json("/analytics", params={"limit": limit})


def request_token(username, password):
    response = requests.post(
        f"{API_BASE_URL}/auth/token",
        json={"username": username, "password": password},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def register_account(username, password):
    response = requests.post(
        f"{API_BASE_URL}/auth/register",
        json={"username": username, "password": password, "role": "analyst"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def render_gauge(score, risk_level):
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": f"Risk Level: {risk_level}"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "black"},
                "steps": [
                    {"range": [0, 40], "color": "#ef4444"},
                    {"range": [40, 70], "color": "#f59e0b"},
                    {"range": [70, 100], "color": "#10b981"},
                ],
            },
        )
    )
    st.plotly_chart(fig, use_container_width=True)


def render_factor_list(factors, title, positive=False):
    st.write(f"#### {title}")
    if not factors:
        st.caption("No major factors in this direction.")
        return

    for factor in factors:
        delta = factor["delta"]
        label = f"+{delta}" if positive else str(delta)
        st.markdown(
            f"**{factor['factor']} ({label})**  \\\nReason: {factor['reason']}  \\\nSource: `{factor['source']}` | Confidence: `{factor['confidence']}`"
        )


def render_summary_cards(result):
    flag_count = len(result.get("red_flags", []))
    confidence_pct = round(result.get("confidence_score", 0.0) * 100, 1)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Trust Score", result.get("trust_score", 0))
    col2.metric("Risk Level", result.get("risk_level", "N/A"))
    col3.metric("Red Flags", flag_count)
    col4.metric("Confidence", f"{confidence_pct}%")


def confidence_label(confidence_score):
    if confidence_score >= 0.8:
        return "High"
    if confidence_score >= 0.6:
        return "Medium"
    return "Low"


def impact_label(delta):
    magnitude = abs(delta)
    if magnitude >= 15:
        return "High Impact"
    if magnitude >= 8:
        return "Medium Impact"
    return "Low Impact"


def simple_reason_text(factor):
    text = factor.get("reason", "").strip()
    return text if text else "Signal change impacted trust score."


def render_user_friendly_xai(result):
    st.write("### Easy Explanation")
    trust_score = result.get("trust_score", 0)
    risk_level = result.get("risk_level", "UNKNOWN")
    confidence_score = float(result.get("confidence_score", 0.0))
    red_flags = result.get("red_flags", [])
    why_score = result.get("why_score", {})
    negatives = why_score.get("top_negative_factors", [])
    positives = why_score.get("top_positive_factors", [])

    st.info(
        f"Final trust score is **{trust_score}/100** with **{risk_level}** risk. "
        f"Confidence is **{confidence_label(confidence_score)}** ({round(confidence_score * 100, 1)}%)."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.write("#### What Reduced Score")
        if negatives:
            for factor in negatives:
                st.markdown(
                    f"- **{factor.get('factor', 'Unknown factor')}** (`{impact_label(int(factor.get('delta', 0)))}`): "
                    f"{simple_reason_text(factor)}"
                )
        else:
            st.success("No major negative drivers detected.")
    with c2:
        st.write("#### What Improved Score")
        if positives:
            for factor in positives:
                st.markdown(
                    f"- **{factor.get('factor', 'Unknown factor')}** (`{impact_label(int(factor.get('delta', 0)))}`): "
                    f"{simple_reason_text(factor)}"
                )
        else:
            st.caption("No strong positive factors detected.")

    st.write("#### What You Should Do Next")
    actions = []
    if any("review" in f.lower() for f in red_flags):
        actions.append("Audit recent reviews/comments for suspicious burst activity.")
    if any("account" in f.lower() for f in red_flags):
        actions.append("Increase profile transparency and publish verifiable identity details.")
    if any("follower" in f.lower() for f in red_flags):
        actions.append("Track follower growth weekly and reduce inorganic audience sources.")
    if not actions:
        actions.append("Maintain current behavior and monitor trust trend over time.")
        actions.append("Re-run investigation weekly to detect sudden pattern shifts.")

    for idx, action in enumerate(actions, start=1):
        st.write(f"{idx}. {action}")


def render_investigation(result):
    render_summary_cards(result)

    if result.get("data_state") != "sufficient_data":
        st.warning(
            f"Data state: `{result.get('data_state')}`. Add a more specific URL/handle for stronger confidence."
        )

    share_url = f"{API_BASE_URL}/investigations/{result.get('scan_id')}" if result.get("scan_id") else "N/A"
    st.caption(
        f"Scan ID: {result.get('scan_id', 'N/A')} | Created: {result.get('created_at', 'N/A')} | "
        f"Last Verified: {result.get('last_verified_at', 'N/A')}"
    )
    st.code(share_url, language="text")

    report_json = json.dumps(result, indent=2)
    st.download_button(
        "Download Investigation JSON",
        data=report_json,
        file_name=f"trustagent_scan_{result.get('scan_id', 'latest')}.json",
        mime="application/json",
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        render_gauge(result.get("trust_score", 0), result.get("risk_level", "UNKNOWN"))

    with col2:
        st.write("### AI Investigation Report")
        st.info(result.get("investigation_report", "No investigation report returned."))

        st.write("### Detected Red Flags")
        red_flags = result.get("red_flags", [])
        if red_flags:
            for flag in red_flags:
                st.error(f"Flag: {flag}")
        else:
            st.success("No critical red flags detected in this run.")

    st.divider()
    render_user_friendly_xai(result)

    st.divider()
    st.write("### Why This Score?")
    c1, c2 = st.columns(2)
    why_score = result.get("why_score", {})
    with c1:
        render_factor_list(why_score.get("top_negative_factors", []), "Top Negative Factors", positive=False)
    with c2:
        render_factor_list(why_score.get("top_positive_factors", []), "Top Positive Factors", positive=True)

    st.divider()
    st.write("### Evidence Mode")
    evidence = result.get("evidence", [])
    if evidence:
        ev_df = pd.DataFrame(evidence)
        cols = ["factor", "reason", "signal", "value", "threshold", "source", "confidence", "last_verified_at", "proof_url"]
        cols = [c for c in cols if c in ev_df.columns]
        st.dataframe(ev_df[cols], use_container_width=True)
    else:
        st.caption("No evidence entries were generated.")

    st.divider()
    c1, c2 = st.columns(2)
    metrics = result.get("metrics", {})

    with c1:
        st.write("#### Follower Authenticity")
        likely_bot, authentic = follower_authenticity_breakdown(metrics)
        fig_pie = px.pie(
            values=[likely_bot, authentic],
            names=["Likely Bot", "Authentic"],
            color_discrete_sequence=["#ef4444", "#10b981"],
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.write("#### Review Sentiment Analysis")
        fig_bar = px.bar(
            x=["Negative", "Neutral", "Positive"],
            y=sentiment_breakdown(metrics),
            labels={"x": "Sentiment", "y": "Count"},
            color=["Negative", "Neutral", "Positive"],
            color_discrete_map={"Negative": "#ef4444", "Neutral": "#f59e0b", "Positive": "#10b981"},
        )
        st.plotly_chart(fig_bar, use_container_width=True)


def render_timeline(target, category):
    st.write("### Trust Timeline")
    try:
        history = get_history(target=target, category=category, limit=25)
        timeline = history.get("timeline", [])
        if not timeline:
            st.caption("No prior scans available for timeline.")
            return

        timeline_df = pd.DataFrame(timeline)
        timeline_df["created_at"] = pd.to_datetime(timeline_df["created_at"])
        fig = px.line(
            timeline_df,
            x="created_at",
            y="trust_score",
            markers=True,
            title=f"Score Trend for {target}",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(timeline_df[["scan_id", "created_at", "trust_score", "risk_level"]], use_container_width=True)
    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to fetch timeline: {exc}")


def render_analytics_panel():
    st.write("### System Analytics")
    try:
        analytics_payload = get_analytics(limit=10)
    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to load analytics: {exc}")
        return

    top_risky = analytics_payload.get("top_risky_targets", [])
    cat_trends = analytics_payload.get("category_trends", [])

    if top_risky:
        risky_df = pd.DataFrame(top_risky)
        st.write("#### Top Risky Targets")
        st.dataframe(risky_df, use_container_width=True)
        fig_risky = px.bar(
            risky_df,
            x="target",
            y="avg_score",
            color="category",
            title="Average Score by Target (Lower is Riskier)",
        )
        st.plotly_chart(fig_risky, use_container_width=True)

    if cat_trends:
        cat_df = pd.DataFrame(cat_trends)
        st.write("#### Risk Trend by Category")
        st.dataframe(cat_df, use_container_width=True)
        fig_cat = px.bar(cat_df, x="category", y="high_risk_count", color="category", title="High-Risk Count by Category")
        st.plotly_chart(fig_cat, use_container_width=True)


st.set_page_config(page_title="TrustAgent AI", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top, #ffffff 0%, #f8fafc 55%, #eef2ff 100%);
        color: #0f172a;
    }
    .block-container {
        padding-top: 1.2rem;
    }
    section[data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    .hero-title {
        text-align: center;
        color: #0f172a;
        margin-bottom: 0.2rem;
    }
    .hero-subtitle {
        text-align: center;
        color: #475569;
        margin-top: 0;
        margin-bottom: 1rem;
        font-size: 1rem;
    }
    [data-testid="stImage"] {
        text-align: center;
    }
    [data-testid="stImage"] img {
        margin-left: auto;
        margin-right: auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

base_dir = Path(__file__).resolve().parent
logo_path = base_dir / "assets" / "logo.png"

if logo_path.exists():
    import base64

    encoded_logo = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
    st.markdown(
        f"""
        <div style="display:flex;justify-content:center;">
            <img src="data:image/png;base64,{encoded_logo}" width="320" />
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<h1 class='hero-title'>TrustAgent AI</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='hero-subtitle'>Autonomous Digital Trust Verification Engine</p>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.write("### Session")
    if st.session_state.get("auth_token"):
        st.success(f"Logged in as {st.session_state.get('auth_user', 'user')}")
        if st.button("Logout"):
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_user", None)
            st.rerun()
    else:
        st.warning("Login required")

if not st.session_state.get("auth_token"):
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        st.write("### Login")
        with st.form("login_form", clear_on_submit=False):
            login_user = st.text_input("Username", value=st.session_state.get("auth_user", ""))
            login_pass = st.text_input("Password", type="password")
            login_submit = st.form_submit_button("Login")

        if login_submit:
            try:
                token_payload = request_token(login_user.strip(), login_pass.strip())
                st.session_state["auth_user"] = login_user.strip()
                st.session_state["auth_token"] = token_payload.get("access_token")
                st.success("Login successful")
                st.rerun()
            except requests.exceptions.HTTPError as exc:
                error_text = exc.response.text[:300] if exc.response is not None else str(exc)
                st.error(f"Login failed: {error_text}")
            except requests.exceptions.RequestException as exc:
                st.error(f"Login failed: {exc}")

    with register_tab:
        st.write("### Register")
        with st.form("register_form", clear_on_submit=True):
            reg_user = st.text_input("New Username")
            reg_pass = st.text_input("New Password", type="password")
            reg_pass2 = st.text_input("Confirm Password", type="password")
            reg_submit = st.form_submit_button("Create Account")

        if reg_submit:
            if reg_pass != reg_pass2:
                st.error("Password and confirm password must match.")
            else:
                try:
                    register_account(reg_user.strip(), reg_pass.strip())
                    st.success("Account created. Please login.")
                except requests.exceptions.HTTPError as exc:
                    error_text = exc.response.text[:300] if exc.response is not None else str(exc)
                    st.error(f"Register failed: {error_text}")
                except requests.exceptions.RequestException as exc:
                    st.error(f"Register failed: {exc}")

    st.stop()

investigate_tab, compare_tab, history_tab, policy_tab = st.tabs(
    ["Investigate", "Compare", "History", "Category Policies"]
)

with investigate_tab:
    st.write("### Single Target Investigation")
    with st.form("investigation_form"):
        target = st.text_input("Enter Handle/URL", placeholder="@fake_store")
        category_label = st.selectbox("Category", list(CATEGORY_LABELS.keys()), key="single_category")
        submit_investigation = st.form_submit_button("Start Investigation")

    if submit_investigation:
        if not target.strip():
            st.warning("Please enter a handle or URL before starting the investigation.")
        else:
            with st.spinner("Agents deployed. Analyzing behavioral signals..."):
                try:
                    payload = {"target": target, "category": CATEGORY_LABELS[category_label]}
                    result = post_json("/investigate", payload)
                    st.session_state["last_investigation"] = result
                except requests.exceptions.HTTPError as exc:
                    error_text = exc.response.text[:400] if exc.response is not None else str(exc)
                    st.error(f"Backend rejected request: {error_text}")
                except requests.exceptions.RequestException as exc:
                    st.error(f"Backend request failed: {exc}")

    if "last_investigation" in st.session_state:
        result = st.session_state["last_investigation"]
        render_investigation(result)
        render_timeline(result.get("target", ""), result.get("category", ""))

with compare_tab:
    st.write("### Compare Two Targets")
    with st.form("compare_form"):
        left_col, right_col = st.columns(2)
        with left_col:
            left_target = st.text_input("Left Target", placeholder="https://instagram.com/entity_a")
            left_category_label = st.selectbox("Left Category", list(CATEGORY_LABELS.keys()), key="left_category")
        with right_col:
            right_target = st.text_input("Right Target", placeholder="https://instagram.com/entity_b")
            right_category_label = st.selectbox("Right Category", list(CATEGORY_LABELS.keys()), key="right_category")

        submit_compare = st.form_submit_button("Run Comparison")

    if submit_compare:
        if not left_target.strip() or not right_target.strip():
            st.warning("Both targets are required for comparison.")
        else:
            with st.spinner("Running side-by-side trust comparison..."):
                try:
                    payload = {
                        "left": {"target": left_target, "category": CATEGORY_LABELS[left_category_label]},
                        "right": {"target": right_target, "category": CATEGORY_LABELS[right_category_label]},
                        "persist": True,
                    }
                    comparison = post_json("/compare", payload)
                    st.session_state["last_comparison"] = comparison
                except requests.exceptions.HTTPError as exc:
                    error_text = exc.response.text[:400] if exc.response is not None else str(exc)
                    st.error(f"Backend rejected comparison: {error_text}")
                except requests.exceptions.RequestException as exc:
                    st.error(f"Comparison request failed: {exc}")

    if "last_comparison" in st.session_state:
        cmp_result = st.session_state["last_comparison"]
        left_res = cmp_result.get("left", {})
        right_res = cmp_result.get("right", {})

        score_df = pd.DataFrame(
            {
                "Target": [left_res.get("target", "N/A"), right_res.get("target", "N/A")],
                "Trust Score": [left_res.get("trust_score", 0), right_res.get("trust_score", 0)],
                "Confidence": [left_res.get("confidence_score", 0.0), right_res.get("confidence_score", 0.0)],
                "Risk Level": [left_res.get("risk_level", "UNKNOWN"), right_res.get("risk_level", "UNKNOWN")],
            }
        )
        st.write("### Comparison Result")
        st.dataframe(score_df, use_container_width=True)
        st.info(
            f"Verdict: `{cmp_result.get('verdict', 'N/A')}` | "
            f"Score Delta (left-right): `{cmp_result.get('score_delta', 'N/A')}`"
        )

        fig_cmp = px.bar(score_df, x="Target", y="Trust Score", color="Risk Level", title="Trust Score Comparison")
        st.plotly_chart(fig_cmp, use_container_width=True)

        lcol, rcol = st.columns(2)
        with lcol:
            render_factor_list(left_res.get("why_score", {}).get("top_negative_factors", []), "Left Top Negative", positive=False)
        with rcol:
            render_factor_list(right_res.get("why_score", {}).get("top_negative_factors", []), "Right Top Negative", positive=False)

with history_tab:
    st.write("### Investigation History")
    h_col1, h_col2, h_col3 = st.columns([2, 2, 1])
    with h_col1:
        h_target = st.text_input("Filter by Target (optional)", placeholder="instagram.com", key="history_target")
    with h_col2:
        category_options = ["All"] + list(CATEGORY_LABELS.keys())
        h_category_label = st.selectbox("Filter by Category", category_options, key="history_category")
    with h_col3:
        h_limit = st.number_input("Limit", min_value=1, max_value=200, value=30, step=1)

    if st.button("Load History"):
        try:
            category_value = None if h_category_label == "All" else CATEGORY_LABELS[h_category_label]
            history_payload = get_history(target=h_target.strip() or None, category=category_value, limit=int(h_limit))
            st.session_state["history_payload"] = history_payload
        except requests.exceptions.RequestException as exc:
            st.error(f"Failed to load history: {exc}")

    if "history_payload" in st.session_state:
        history_payload = st.session_state["history_payload"]
        timeline = history_payload.get("timeline", [])
        investigations = history_payload.get("investigations", [])
        st.caption(f"Records loaded: {history_payload.get('count', 0)}")

        if timeline:
            timeline_df = pd.DataFrame(timeline)
            timeline_df["created_at"] = pd.to_datetime(timeline_df["created_at"])
            fig_hist = px.line(timeline_df, x="created_at", y="trust_score", color="target", markers=True)
            st.plotly_chart(fig_hist, use_container_width=True)

        if investigations:
            rows = [
                {
                    "scan_id": i.get("scan_id"),
                    "created_at": i.get("created_at"),
                    "target": i.get("target"),
                    "category": i.get("category"),
                    "trust_score": i.get("trust_score", 0),
                    "confidence_score": i.get("confidence_score", 0.0),
                    "data_state": i.get("data_state", "sufficient_data"),
                    "risk_level": i.get("risk_level", "UNKNOWN"),
                    "red_flag_count": len(i.get("red_flags", [])),
                }
                for i in investigations
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    render_analytics_panel()

with policy_tab:
    st.write("### Category Policy Cards")
    for category_key, checks in POLICY_CHECKS.items():
        with st.expander(f"{category_key.upper()} policy"):
            for idx, check in enumerate(checks, start=1):
                st.write(f"{idx}. {check}")
