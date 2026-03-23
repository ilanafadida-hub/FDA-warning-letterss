"""
FDA Warning Letter Analysis Dashboard.

Interactive Streamlit app for searching, filtering, visualizing,
and analyzing FDA warning letters.

Run with: streamlit run dashboard.py
"""

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from config import METADATA_CSV, TEXTS_CSV, SUMMARIES_CSV, DATA_DIR, OPENAI_API_KEY, ensure_data_dir, load_status

# ── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FDA Warning Letter Analysis",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── CFR Link Helper ────────────────────────────────────────────────────────

def cfr_to_link(citation):
    """
    Convert a CFR citation like '21 CFR 211.67' into a clickable eCFR link.
    Handles formats: '21 CFR 211.67', '21 CFR 211.67(a)', '21 CFR Part 211'
    """
    import re
    # Extract part and section numbers
    m = re.match(r'21\s*C\.?F\.?R\.?\s*(?:Part\s*)?(\d+)(?:\.(\d+))?(.*)$', citation.strip())
    if not m:
        return citation  # Can't parse, return plain text

    part = m.group(1)
    section = m.group(2)
    remainder = m.group(3).strip() if m.group(3) else ""

    if section:
        url = f"https://www.ecfr.gov/current/title-21/part-{part}/section-{part}.{section}"
        display = f"21 CFR {part}.{section}{remainder}"
    else:
        url = f"https://www.ecfr.gov/current/title-21/part-{part}"
        display = f"21 CFR Part {part}{remainder}"

    return f"[{display}]({url})"


def cfr_list_to_markdown(violations):
    """Convert a list of CFR citations to markdown with clickable links."""
    lines = []
    for v in violations:
        lines.append(f"- {cfr_to_link(v)}")
    return "\n".join(lines)


# ── Data Loading ───────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    """Load and merge all CSV data files."""
    ensure_data_dir()

    # Load metadata
    if METADATA_CSV.exists():
        meta = pd.read_csv(METADATA_CSV)
    else:
        return pd.DataFrame()

    # Parse dates
    for col in ["posted_date", "letter_date"]:
        if col in meta.columns:
            meta[col] = pd.to_datetime(meta[col], format="mixed", errors="coerce")

    # Add year column
    if "letter_date" in meta.columns:
        meta["year"] = meta["letter_date"].dt.year
        meta["quarter"] = meta["letter_date"].dt.to_period("Q").astype(str)

    # Merge with texts
    if TEXTS_CSV.exists():
        texts = pd.read_csv(TEXTS_CSV)
        meta = meta.merge(texts, on="url", how="left", suffixes=("", "_text"))

    # Merge with summaries
    if SUMMARIES_CSV.exists():
        summaries = pd.read_csv(SUMMARIES_CSV)
        meta = meta.merge(summaries, on="url", how="left", suffixes=("", "_summary"))

    return meta


def parse_json_col(series):
    """Safely parse a JSON list column, returning empty list for failures."""
    def _parse(val):
        if pd.isna(val):
            return []
        try:
            result = json.loads(val)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return series.apply(_parse)


# ── Search & Filter ───────────────────────────────────────────────────────

def apply_filters(df, search_text, years, offices, product_types):
    """Apply all sidebar filters to the dataframe."""
    filtered = df.copy()

    # Year filter
    if years and "year" in filtered.columns:
        filtered = filtered[filtered["year"].isin(years)]

    # Office filter
    if offices:
        filtered = filtered[filtered["issuing_office"].isin(offices)]

    # Product type filter (check both subject and product_type columns)
    if product_types:
        mask = pd.Series(False, index=filtered.index)
        for pt in product_types:
            pt_lower = pt.lower()
            if "subject" in filtered.columns:
                mask |= filtered["subject"].fillna("").str.lower().str.contains(pt_lower, na=False)
            if "product_type" in filtered.columns:
                mask |= filtered["product_type"].fillna("").str.lower().str.contains(pt_lower, na=False)
            if "product_types" in filtered.columns:
                mask |= filtered["product_types"].fillna("").str.lower().str.contains(pt_lower, na=False)
        filtered = filtered[mask]

    # Text search (across multiple columns)
    if search_text:
        search_lower = search_text.lower()
        text_cols = ["company", "subject", "full_text", "summary", "key_observations"]
        mask = pd.Series(False, index=filtered.index)
        for col in text_cols:
            if col in filtered.columns:
                mask |= filtered[col].fillna("").str.lower().str.contains(search_lower, na=False)
        filtered = filtered[mask]

    return filtered


# ── Sidebar ────────────────────────────────────────────────────────────────

def render_sidebar(df):
    """Render sidebar filters and return filter values."""
    st.sidebar.title("🔍 Filters")

    # Search box
    search_text = st.sidebar.text_input(
        "Search (company, subject, observations, full text)",
        placeholder="e.g., cleaning, data integrity, CGMP...",
    )

    # Year filter
    if "year" in df.columns:
        available_years = sorted(df["year"].dropna().unique().astype(int).tolist(), reverse=True)
        selected_years = st.sidebar.multiselect("Year", available_years)
    else:
        selected_years = []

    # Issuing office filter
    if "issuing_office" in df.columns:
        offices = sorted(df["issuing_office"].dropna().unique().tolist())
        selected_offices = st.sidebar.multiselect("Issuing Office", offices)
    else:
        selected_offices = []

    # Product type filter
    product_type_options = [
        "Drugs", "CGMP", "Devices", "Biologics", "Food",
        "Dietary Supplements", "Cosmetics", "Tobacco", "Veterinary",
    ]
    selected_product_types = st.sidebar.multiselect("Product Type", product_type_options)

    # Refresh button
    st.sidebar.markdown("---")
    if st.sidebar.button("Update Data (fetch new only)", use_container_width=True):
        refresh_data()

    # Data info & last updated status
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Total letters: {len(df)}")
    if "year" in df.columns:
        date_range = df["year"].dropna()
        if len(date_range) > 0:
            st.sidebar.caption(f"Date range: {int(date_range.min())} - {int(date_range.max())}")

    # Show last updated timestamps
    status = load_status()
    if status:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Last Updated**")
        if "metadata_fetch" in status:
            meta_info = status["metadata_fetch"]
            st.sidebar.caption(
                f"Metadata: {meta_info.get('date', 'N/A')}\n"
                f"({meta_info.get('total_records', '?')} records, {meta_info.get('new_records', '?')} new)"
            )
        if "text_fetch" in status:
            text_info = status["text_fetch"]
            st.sidebar.caption(
                f"Full texts: {text_info.get('date', 'N/A')}\n"
                f"({text_info.get('total_with_text', '?')} letters with text)"
            )
        if "summarization" in status:
            sum_info = status["summarization"]
            st.sidebar.caption(
                f"Summaries: {sum_info.get('date', 'N/A')}\n"
                f"({sum_info.get('total_summaries', '?')} total, {sum_info.get('method', '')})"
            )

    return search_text, selected_years, selected_offices, selected_product_types


def refresh_data():
    """Run fetch and summarize scripts, then clear cache."""
    with st.spinner("Fetching new data from FDA... This may take several minutes."):
        try:
            subprocess.run([sys.executable, "fetch_fda_data.py"], check=True, capture_output=True)
            st.success("Data fetched successfully!")
        except subprocess.CalledProcessError as e:
            st.error(f"Fetch failed: {e.stderr.decode() if e.stderr else str(e)}")
            return

    with st.spinner("Summarizing new letters..."):
        try:
            subprocess.run([sys.executable, "summarize_letters.py"], check=True, capture_output=True)
            st.success("Summarization complete!")
        except subprocess.CalledProcessError as e:
            st.error(f"Summarization failed: {e.stderr.decode() if e.stderr else str(e)}")

    st.cache_data.clear()
    st.rerun()


# ── Tab 1: Letters Table ──────────────────────────────────────────────────

def render_letters_table(filtered_df):
    """Render the searchable letters table."""
    st.subheader(f"📋 Warning Letters ({len(filtered_df)} results)")

    if len(filtered_df) == 0:
        st.info("No letters match your filters. Try broadening your search.")
        return

    # Display columns
    display_cols = ["letter_date", "company", "issuing_office", "subject"]
    if "summary" in filtered_df.columns:
        display_cols.append("summary")

    display_df = filtered_df[
        [c for c in display_cols if c in filtered_df.columns]
    ].copy()

    # Format date
    if "letter_date" in display_df.columns:
        display_df["letter_date"] = display_df["letter_date"].dt.strftime("%Y-%m-%d")

    # Rename for display
    col_names = {
        "letter_date": "Date",
        "company": "Company",
        "issuing_office": "Issuing Office",
        "subject": "Subject",
        "summary": "Summary",
    }
    display_df = display_df.rename(columns=col_names)

    st.dataframe(display_df, use_container_width=True, height=500)

    # Export button
    csv_data = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Export filtered results to CSV",
        csv_data,
        file_name="fda_warning_letters_filtered.csv",
        mime="text/csv",
    )

    # Expandable letter details
    st.markdown("---")
    st.subheader("📄 Letter Details")

    for i, (_, row) in enumerate(filtered_df.head(50).iterrows()):
        company = row.get("company", "Unknown")
        date_str = row["letter_date"].strftime("%Y-%m-%d") if pd.notna(row.get("letter_date")) else "N/A"

        with st.expander(f"{company} — {date_str}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Company:** {company}")
                st.markdown(f"**Date:** {date_str}")
                st.markdown(f"**Office:** {row.get('issuing_office', 'N/A')}")
            with col2:
                st.markdown(f"**Subject:** {row.get('subject', 'N/A')}")
                if row.get("fei_number"):
                    st.markdown(f"**FEI:** {row['fei_number']}")
                if row.get("reference_number"):
                    st.markdown(f"**Ref:** {row['reference_number']}")

            # Summary
            if pd.notna(row.get("summary")):
                st.markdown("**Summary:**")
                st.write(row["summary"])

            # Key observations
            if pd.notna(row.get("key_observations")):
                try:
                    obs = json.loads(row["key_observations"])
                    if obs:
                        st.markdown("**Key Observations:**")
                        for o in obs:
                            st.markdown(f"- {o}")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Violations
            if pd.notna(row.get("violations")):
                try:
                    viols = json.loads(row["violations"])
                    if viols:
                        st.markdown("**CFR Violations:**")
                        st.markdown(cfr_list_to_markdown(viols), unsafe_allow_html=True)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Full text
            if pd.notna(row.get("full_text")) and len(str(row["full_text"])) > 50:
                st.markdown("**Full Letter Text:**")
                st.text_area("", value=str(row["full_text"])[:5000], height=200,
                             disabled=True, key=f"text_{row.get('url', i)}")
                if len(str(row["full_text"])) > 5000:
                    st.caption("(Text truncated to 5000 characters)")


# ── Tab 2: Trends & Visualizations ────────────────────────────────────────

def render_trends(filtered_df):
    """Render trends and visualization charts."""
    st.subheader("📈 Trends & Visualizations")

    if len(filtered_df) == 0:
        st.info("No data to visualize. Try broadening your filters.")
        return

    # ── Letters over time ──
    if "year" in filtered_df.columns:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Letters by Year")
            yearly = filtered_df.groupby("year").size().reset_index(name="count")
            yearly = yearly.dropna()
            chart = alt.Chart(yearly).mark_bar(color="#1f77b4").encode(
                x=alt.X("year:O", title="Year"),
                y=alt.Y("count:Q", title="Number of Letters"),
                tooltip=["year:O", "count:Q"],
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

        with col2:
            st.markdown("#### Letters by Quarter")
            if "quarter" in filtered_df.columns:
                quarterly = filtered_df.groupby("quarter").size().reset_index(name="count")
                quarterly = quarterly.sort_values("quarter").tail(20)  # Last 20 quarters
                chart = alt.Chart(quarterly).mark_line(point=True, color="#ff7f0e").encode(
                    x=alt.X("quarter:O", title="Quarter"),
                    y=alt.Y("count:Q", title="Number of Letters"),
                    tooltip=["quarter:O", "count:Q"],
                ).properties(height=350)
                st.altair_chart(chart, use_container_width=True)

    # ── Issuing Office breakdown ──
    if "issuing_office" in filtered_df.columns:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### By Issuing Office")
            office_counts = filtered_df["issuing_office"].value_counts().head(10).reset_index()
            office_counts.columns = ["office", "count"]
            chart = alt.Chart(office_counts).mark_bar(color="#2ca02c").encode(
                x=alt.X("count:Q", title="Number of Letters"),
                y=alt.Y("office:N", title="", sort="-x"),
                tooltip=["office:N", "count:Q"],
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

        with col2:
            # Heatmap: Office × Year
            if "year" in filtered_df.columns:
                st.markdown("#### Office × Year Heatmap")
                heatmap_data = filtered_df.groupby(["issuing_office", "year"]).size().reset_index(name="count")
                # Top 6 offices for readability
                top_offices = filtered_df["issuing_office"].value_counts().head(6).index.tolist()
                heatmap_data = heatmap_data[heatmap_data["issuing_office"].isin(top_offices)]

                chart = alt.Chart(heatmap_data).mark_rect().encode(
                    x=alt.X("year:O", title="Year"),
                    y=alt.Y("issuing_office:N", title=""),
                    color=alt.Color("count:Q", scale=alt.Scale(scheme="blues"), title="Letters"),
                    tooltip=["issuing_office:N", "year:O", "count:Q"],
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)

    # ── Top Violations ──
    if "violations" in filtered_df.columns:
        st.markdown("#### Top CFR Violations Cited")
        all_violations = []
        for v in filtered_df["violations"].dropna():
            try:
                viols = json.loads(v)
                all_violations.extend(viols)
            except (json.JSONDecodeError, TypeError):
                pass

        if all_violations:
            viol_counts = Counter(all_violations).most_common(15)
            viol_df = pd.DataFrame(viol_counts, columns=["violation", "count"])
            chart = alt.Chart(viol_df).mark_bar(color="#d62728").encode(
                x=alt.X("count:Q", title="Times Cited"),
                y=alt.Y("violation:N", title="", sort="-x"),
                tooltip=["violation:N", "count:Q"],
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)

            # Clickable links for top violations
            st.markdown("**Click to view regulation:**")
            st.markdown(cfr_list_to_markdown([v for v, _ in viol_counts[:10]]), unsafe_allow_html=True)

    # ── Top Observation Keywords ──
    if "key_observations" in filtered_df.columns:
        st.markdown("#### Most Common Observation Keywords")
        all_words = []
        stop_words = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "is",
                       "was", "were", "are", "be", "been", "being", "have", "has", "had",
                       "do", "does", "did", "not", "no", "your", "you", "that", "this",
                       "with", "from", "by", "at", "it", "its", "as", "but", "if", "we",
                       "our", "their", "they", "there", "which", "what", "when", "where",
                       "how", "all", "each", "than", "also", "any", "firm", "did"}
        for obs_json in filtered_df["key_observations"].dropna():
            try:
                obs_list = json.loads(obs_json)
                for obs in obs_list:
                    words = obs.lower().split()
                    all_words.extend(w for w in words if len(w) > 3 and w not in stop_words)
            except (json.JSONDecodeError, TypeError):
                pass

        if all_words:
            word_counts = Counter(all_words).most_common(20)
            word_df = pd.DataFrame(word_counts, columns=["keyword", "count"])
            chart = alt.Chart(word_df).mark_bar(color="#9467bd").encode(
                x=alt.X("count:Q", title="Frequency"),
                y=alt.Y("keyword:N", title="", sort="-x"),
                tooltip=["keyword:N", "count:Q"],
            ).properties(height=500)
            st.altair_chart(chart, use_container_width=True)


# ── Tab 3: Insights & Q&A ────────────────────────────────────────────────

def render_insights(df, filtered_df):
    """Render insights, metrics, and Q&A interface."""
    st.subheader("💡 Insights & Q&A")

    if len(df) == 0:
        st.info("No data available. Fetch data first using the Refresh button.")
        return

    # ── Q&A Chat Interface (placed first for easy access) ──
    st.markdown("#### 💬 Ask a Question About the Data")
    st.caption("Ask questions like: 'Which companies received multiple warning letters?', "
               "'What are the most common violations in 2024?', 'Show trends in cleaning observations'")

    user_question = st.text_input("Your question:", placeholder="e.g., What are the top violations in food safety?")

    if user_question:
        answer = answer_question(user_question, df, filtered_df)
        st.markdown("**Answer:**")
        st.write(answer)

    st.markdown("---")

    # ── Key Metrics Cards ──
    st.markdown("#### Key Metrics")
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric("Total Letters", len(df))
    with m2:
        current_year = datetime.now().year
        this_year = len(df[df.get("year", pd.Series()) == current_year]) if "year" in df.columns else 0
        st.metric(f"Letters in {current_year}", this_year)
    with m3:
        if "issuing_office" in df.columns:
            top_office = df["issuing_office"].mode().iloc[0] if len(df) > 0 else "N/A"
            st.metric("Most Active Office", top_office[:30])
        else:
            st.metric("Most Active Office", "N/A")
    with m4:
        # Repeat offenders
        if "company" in df.columns:
            company_counts = df["company"].value_counts()
            repeat = (company_counts > 1).sum()
            st.metric("Repeat Offenders", repeat)
        else:
            st.metric("Repeat Offenders", "N/A")

    st.markdown("---")

    # ── Auto-Generated Insights ──
    st.markdown("#### Auto-Generated Insights")

    insights = generate_insights(df)
    for insight in insights:
        st.markdown(f"- {insight}")

    st.markdown("---")

    # ── Year-over-Year Comparison ──
    st.markdown("#### Compare Two Years")
    if "year" in df.columns:
        available_years = sorted(df["year"].dropna().unique().astype(int).tolist(), reverse=True)
        if len(available_years) >= 2:
            comp_col1, comp_col2 = st.columns(2)
            with comp_col1:
                year1 = st.selectbox("Year A", available_years, index=0)
            with comp_col2:
                year2 = st.selectbox("Year B", available_years, index=min(1, len(available_years) - 1))

            if year1 != year2:
                df_y1 = df[df["year"] == year1]
                df_y2 = df[df["year"] == year2]

                c1, c2, c3 = st.columns(3)
                with c1:
                    delta = len(df_y1) - len(df_y2)
                    st.metric(f"Letters in {year1}", len(df_y1), delta=f"{delta:+d} vs {year2}")
                with c2:
                    if "issuing_office" in df.columns:
                        top1 = df_y1["issuing_office"].mode().iloc[0] if len(df_y1) > 0 else "N/A"
                        st.metric(f"Top Office ({year1})", top1[:30])
                with c3:
                    if "issuing_office" in df.columns:
                        top2 = df_y2["issuing_office"].mode().iloc[0] if len(df_y2) > 0 else "N/A"
                        st.metric(f"Top Office ({year2})", top2[:30])

    st.markdown("---")

    # ── Observations & Responses Review ──
    render_observations_and_responses(filtered_df)

    st.markdown("---")

    # ── Acceptable Responses Reference ──
    render_acceptable_responses()



def render_observations_and_responses(df):
    """Show paired observations and corrective actions from letters."""
    st.markdown("#### Observations & Responses Review")
    st.caption("See what FDA observed and what corrective actions were required")

    if len(df) == 0 or "key_observations" not in df.columns:
        st.info("No observation data available.")
        return

    # Let user filter by theme
    theme_filter = st.selectbox(
        "Filter by observation theme:",
        ["All", "Cleaning", "Data Integrity", "Contamination", "Validation",
         "Documentation", "Training", "Sterility", "Labeling", "Equipment",
         "Testing", "CAPA", "Storage"],
        key="obs_theme_filter",
    )

    # Collect observation-response pairs
    pairs = []
    for _, row in df.iterrows():
        try:
            obs_list = json.loads(row["key_observations"]) if pd.notna(row.get("key_observations")) else []
            actions_list = json.loads(row["corrective_actions"]) if pd.notna(row.get("corrective_actions")) else []
            violations = json.loads(row["violations"]) if pd.notna(row.get("violations")) else []
        except (json.JSONDecodeError, TypeError):
            continue

        if not obs_list:
            continue

        # Apply theme filter
        if theme_filter != "All":
            theme_lower = theme_filter.lower()
            obs_text = " ".join(obs_list).lower()
            if theme_lower not in obs_text:
                continue

        company = row.get("company", "Unknown")
        year = int(row["year"]) if pd.notna(row.get("year")) else "N/A"
        office = row.get("issuing_office", "N/A")

        pairs.append({
            "company": company,
            "year": year,
            "office": office,
            "observations": obs_list,
            "corrective_actions": actions_list,
            "violations": violations,
        })

    if not pairs:
        st.info(f"No observations found matching '{theme_filter}'.")
        return

    st.markdown(f"**Found {len(pairs)} letters with matching observations**")

    # Show as expandable cards (limit to 30 for performance)
    for p in pairs[:30]:
        with st.expander(f"{p['company']} ({p['year']}) - {p['office'][:40]}"):
            col_obs, col_resp = st.columns(2)

            with col_obs:
                st.markdown("**FDA Observations:**")
                for i, obs in enumerate(p["observations"][:10], 1):
                    st.markdown(f"{i}. {obs[:200]}")

                if p["violations"]:
                    st.markdown("**Cited Regulations:**")
                    st.markdown(cfr_list_to_markdown(p["violations"][:5]), unsafe_allow_html=True)

            with col_resp:
                st.markdown("**Required Corrective Actions:**")
                if p["corrective_actions"]:
                    for i, action in enumerate(p["corrective_actions"][:10], 1):
                        st.markdown(f"{i}. {action[:200]}")
                else:
                    st.markdown("_No specific corrective actions extracted._")

    if len(pairs) > 30:
        st.caption(f"Showing 30 of {len(pairs)} matching letters. Use filters to narrow down.")


def render_acceptable_responses():
    """
    Show a reference guide of acceptable responses to common FDA observations.
    This is a QA reference based on FDA guidance documents.
    """
    st.markdown("#### Acceptable Response Reference Guide")
    st.caption("Common FDA observations and recommended response strategies for QA teams")

    acceptable_responses = {
        "Cleaning & Sanitation": {
            "common_observations": [
                "Failure to clean equipment to prevent contamination",
                "Inadequate cleaning validation",
                "No written cleaning procedures",
            ],
            "recommended_responses": [
                "Develop and validate cleaning procedures with acceptance criteria",
                "Perform cleaning validation studies with worst-case scenarios",
                "Establish monitoring program with swab/rinse sampling",
                "Document cleaning logs with dates, methods, and operator signatures",
                "Train all personnel on cleaning SOPs",
            ],
            "key_regulations": ["21 CFR 211.67", "21 CFR 211.182"],
        },
        "Data Integrity": {
            "common_observations": [
                "Failure to maintain complete and accurate records",
                "Unauthorized data changes without audit trail",
                "Backdating or falsifying laboratory records",
            ],
            "recommended_responses": [
                "Implement ALCOA+ data integrity principles across all systems",
                "Ensure audit trails are enabled and regularly reviewed",
                "Conduct data integrity risk assessment and remediation",
                "Hire qualified third-party auditor for retrospective data review",
                "Establish data governance policy with clear roles and responsibilities",
            ],
            "key_regulations": ["21 CFR 211.68", "21 CFR 211.188", "21 CFR 211.194"],
        },
        "CAPA (Corrective & Preventive Actions)": {
            "common_observations": [
                "Failure to investigate failures and deviations",
                "Inadequate CAPA effectiveness checks",
                "No root cause analysis for recurring issues",
            ],
            "recommended_responses": [
                "Implement formal CAPA system with defined timelines",
                "Use root cause analysis tools (fishbone, 5-why, fault tree)",
                "Verify and validate effectiveness of each CAPA",
                "Track CAPA metrics and trending for management review",
                "Ensure CAPAs address systemic issues, not just symptoms",
            ],
            "key_regulations": ["21 CFR 211.192", "21 CFR 820.90"],
        },
        "Contamination / Cross-Contamination": {
            "common_observations": [
                "Failure to prevent contamination of drug products",
                "Inadequate air handling systems",
                "No environmental monitoring program",
            ],
            "recommended_responses": [
                "Qualify HVAC systems and validate air classifications",
                "Implement environmental monitoring with alert/action limits",
                "Perform media fill studies for aseptic operations",
                "Establish gowning qualification programs",
                "Conduct risk assessments for cross-contamination prevention",
            ],
            "key_regulations": ["21 CFR 211.42", "21 CFR 211.46", "21 CFR 211.113"],
        },
        "Laboratory Controls": {
            "common_observations": [
                "Failure to test each batch for identity and strength",
                "Out-of-specification results not properly investigated",
                "No stability testing program",
            ],
            "recommended_responses": [
                "Test all batches per approved specifications before release",
                "Implement OOS investigation procedure per FDA guidance",
                "Establish ongoing stability program per ICH guidelines",
                "Qualify and calibrate all laboratory instruments",
                "Validate all analytical methods",
            ],
            "key_regulations": ["21 CFR 211.160", "21 CFR 211.165", "21 CFR 211.166"],
        },
        "Documentation & Records": {
            "common_observations": [
                "Incomplete batch production records",
                "Missing SOPs for critical operations",
                "Failure to follow written procedures",
            ],
            "recommended_responses": [
                "Review and update all SOPs to reflect current practices",
                "Implement document control system with version tracking",
                "Ensure batch records are completed contemporaneously",
                "Train operators on documentation practices",
                "Conduct periodic SOP review and updates",
            ],
            "key_regulations": ["21 CFR 211.186", "21 CFR 211.188", "21 CFR 211.192"],
        },
        "Training": {
            "common_observations": [
                "Personnel lack training on CGMP requirements",
                "No training records for production personnel",
                "Inadequate training on specific job functions",
            ],
            "recommended_responses": [
                "Develop comprehensive training program with competency assessments",
                "Maintain training records with dates, topics, and trainers",
                "Include CGMP, job-specific, and safety training",
                "Conduct annual refresher training",
                "Verify training effectiveness through practical assessments",
            ],
            "key_regulations": ["21 CFR 211.25"],
        },
        "Validation": {
            "common_observations": [
                "Process validation not performed or inadequate",
                "No computer system validation",
                "Equipment not qualified (IQ/OQ/PQ)",
            ],
            "recommended_responses": [
                "Implement process validation lifecycle approach (FDA 2011 guidance)",
                "Qualify all critical equipment (IQ, OQ, PQ)",
                "Validate computerized systems per 21 CFR Part 11",
                "Establish continued process verification program",
                "Document validation protocols and reports",
            ],
            "key_regulations": ["21 CFR 211.68", "21 CFR 211.100", "21 CFR Part 11"],
        },
    }

    selected_category = st.selectbox(
        "Select observation category:",
        list(acceptable_responses.keys()),
        key="acceptable_resp_category",
    )

    info = acceptable_responses[selected_category]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Common FDA Observations:**")
        for obs in info["common_observations"]:
            st.markdown(f"- {obs}")

        st.markdown("**Key Regulations:**")
        st.markdown(cfr_list_to_markdown(info["key_regulations"]), unsafe_allow_html=True)

    with col2:
        st.markdown("**Recommended Response Strategy:**")
        for i, resp in enumerate(info["recommended_responses"], 1):
            st.markdown(f"{i}. {resp}")


def generate_insights(df):
    """Generate automatic insights from the data."""
    insights = []

    if len(df) == 0:
        return ["No data available for insights."]

    current_year = datetime.now().year
    prev_year = current_year - 1

    if "year" in df.columns:
        # Year-over-year change
        this_year_count = len(df[df["year"] == current_year])
        last_year_count = len(df[df["year"] == prev_year])
        if last_year_count > 0:
            change_pct = ((this_year_count - last_year_count) / last_year_count) * 100
            direction = "increased" if change_pct > 0 else "decreased"
            insights.append(
                f"Warning letters {direction} by {abs(change_pct):.0f}% in {current_year} "
                f"({this_year_count}) vs {prev_year} ({last_year_count})."
            )

    # Most active office this year
    if "issuing_office" in df.columns and "year" in df.columns:
        this_year_df = df[df["year"] == current_year]
        if len(this_year_df) > 0:
            top_office = this_year_df["issuing_office"].value_counts()
            if len(top_office) > 0:
                insights.append(
                    f"In {current_year}, {top_office.index[0]} issued the most letters ({top_office.iloc[0]})."
                )

    # Repeat offenders
    if "company" in df.columns:
        company_counts = df["company"].value_counts()
        top_repeaters = company_counts[company_counts > 2]
        if len(top_repeaters) > 0:
            insights.append(
                f"{len(top_repeaters)} companies received 3+ warning letters. "
                f"Top: {top_repeaters.index[0]} ({top_repeaters.iloc[0]} letters)."
            )

    # Top violations trend
    if "violations" in df.columns:
        all_violations = []
        for v in df["violations"].dropna():
            try:
                all_violations.extend(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                pass
        if all_violations:
            top_viol = Counter(all_violations).most_common(1)
            insights.append(f"Most cited regulation: {top_viol[0][0]} ({top_viol[0][1]} citations).")

    # Common observation themes
    if "key_observations" in df.columns:
        themes = {"cleaning": 0, "data integrity": 0, "validation": 0, "contamination": 0,
                  "documentation": 0, "training": 0, "sterility": 0, "labeling": 0}
        for obs_json in df["key_observations"].dropna():
            try:
                obs_list = json.loads(obs_json)
                obs_text = " ".join(obs_list).lower()
                for theme in themes:
                    if theme in obs_text:
                        themes[theme] += 1
            except (json.JSONDecodeError, TypeError):
                pass

        top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
        top_themes = [(t, c) for t, c in top_themes if c > 0]
        if top_themes:
            theme_str = ", ".join(f"{t} ({c})" for t, c in top_themes)
            insights.append(f"Top observation themes: {theme_str}.")

    if not insights:
        insights.append("Not enough data to generate meaningful insights yet.")

    return insights


def answer_question(question, full_df, filtered_df):
    """
    Answer a user question about the data.
    Uses Claude API if available, otherwise falls back to rule-based stats.
    """
    q = question.lower()

    # Try Claude API first
    if OPENAI_API_KEY:
        try:
            return _answer_with_openai(question, filtered_df)
        except Exception as e:
            st.warning(f"Claude API error: {e}. Using statistical analysis instead.")

    # Rule-based answers
    if any(w in q for w in ["multiple", "repeat", "more than one", "several times"]):
        if "company" in full_df.columns:
            counts = full_df["company"].value_counts()
            repeaters = counts[counts > 1].head(10)
            if len(repeaters) > 0:
                result = "**Companies with multiple warning letters:**\n\n"
                for company, count in repeaters.items():
                    result += f"- {company}: {count} letters\n"
                return result
        return "No repeat offender data available."

    if any(w in q for w in ["common", "top", "most", "frequent"]):
        if any(w in q for w in ["violation", "cfr", "regulation"]):
            if "violations" in full_df.columns:
                all_v = []
                for v in filtered_df["violations"].dropna():
                    try:
                        all_v.extend(json.loads(v))
                    except (json.JSONDecodeError, TypeError):
                        pass
                if all_v:
                    top = Counter(all_v).most_common(10)
                    result = "**Top violations cited:**\n\n"
                    for viol, count in top:
                        result += f"- {viol}: {count} times\n"
                    return result

        if any(w in q for w in ["observation", "finding", "issue"]):
            if "key_observations" in full_df.columns:
                themes = {}
                for obs_json in filtered_df["key_observations"].dropna():
                    try:
                        for obs in json.loads(obs_json):
                            for word in obs.lower().split():
                                if len(word) > 4:
                                    themes[word] = themes.get(word, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass
                if themes:
                    top = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:10]
                    result = "**Most common observation keywords:**\n\n"
                    for word, count in top:
                        result += f"- {word}: {count} mentions\n"
                    return result

    if any(w in q for w in ["trend", "over time", "increasing", "decreasing"]):
        if "year" in filtered_df.columns:
            yearly = filtered_df.groupby("year").size()
            result = "**Letters per year:**\n\n"
            for year, count in yearly.items():
                result += f"- {int(year)}: {count} letters\n"
            return result

    # Generic stats for the filtered dataset
    result = f"**Based on {len(filtered_df)} filtered letters:**\n\n"
    if "issuing_office" in filtered_df.columns:
        result += f"- Top office: {filtered_df['issuing_office'].mode().iloc[0] if len(filtered_df) > 0 else 'N/A'}\n"
    if "year" in filtered_df.columns:
        result += f"- Year range: {int(filtered_df['year'].min())} - {int(filtered_df['year'].max())}\n"
    result += f"\nFor more detailed answers, add your Anthropic API key to .env file."
    return result


def _answer_with_openai(question, df):
    """Use OpenAI API to answer questions about the data."""
    from openai import OpenAI

    # Prepare a data summary for GPT
    summary_lines = [f"Dataset: {len(df)} FDA warning letters"]

    if "year" in df.columns:
        yearly = df.groupby("year").size().to_dict()
        summary_lines.append(f"Letters by year: {yearly}")

    if "issuing_office" in df.columns:
        offices = df["issuing_office"].value_counts().head(5).to_dict()
        summary_lines.append(f"Top offices: {offices}")

    if "company" in df.columns:
        repeaters = df["company"].value_counts()
        top_repeaters = repeaters[repeaters > 1].head(10).to_dict()
        if top_repeaters:
            summary_lines.append(f"Companies with multiple letters: {top_repeaters}")

    if "violations" in df.columns:
        all_v = []
        for v in df["violations"].dropna():
            try:
                all_v.extend(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                pass
        if all_v:
            top_v = Counter(all_v).most_common(10)
            summary_lines.append(f"Top violations: {top_v}")

    if "subject" in df.columns:
        subjects = df["subject"].value_counts().head(10).to_dict()
        summary_lines.append(f"Top subjects: {subjects}")

    data_context = "\n".join(summary_lines)

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1000,
        messages=[
            {"role": "system", "content": "You are an FDA regulatory data analyst. Answer questions about warning letter data concisely. Use the data summary provided."},
            {"role": "user", "content": f"Data summary:\n{data_context}\n\nQuestion: {question}"},
        ],
    )
    return response.choices[0].message.content


# ── Tab 4: Letter Detail ─────────────────────────────────────────────────

def render_letter_detail(df):
    """Render detailed view for a single letter."""
    st.subheader("📄 Letter Detail View")

    if len(df) == 0:
        st.info("No letters available.")
        return

    # Letter selector
    options = []
    for _, row in df.iterrows():
        company = row.get("company", "Unknown")
        date_str = row["letter_date"].strftime("%Y-%m-%d") if pd.notna(row.get("letter_date")) else "N/A"
        options.append(f"{company} — {date_str}")

    selected = st.selectbox("Select a letter:", options)
    if selected:
        idx = options.index(selected)
        row = df.iloc[idx]

        # Metadata
        st.markdown("### Metadata")
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.markdown(f"**Company:** {row.get('company', 'N/A')}")
            st.markdown(f"**Letter Date:** {row['letter_date'].strftime('%Y-%m-%d') if pd.notna(row.get('letter_date')) else 'N/A'}")
            st.markdown(f"**Posted Date:** {row['posted_date'].strftime('%Y-%m-%d') if pd.notna(row.get('posted_date')) else 'N/A'}")
        with meta_col2:
            st.markdown(f"**Issuing Office:** {row.get('issuing_office', 'N/A')}")
            st.markdown(f"**Subject:** {row.get('subject', 'N/A')}")
            if row.get("fei_number"):
                st.markdown(f"**FEI Number:** {row['fei_number']}")
            if row.get("reference_number"):
                st.markdown(f"**Reference:** {row['reference_number']}")
            if row.get("facility_address"):
                st.markdown(f"**Facility:** {row['facility_address']}")

        # Summary
        if pd.notna(row.get("summary")):
            st.markdown("### Summary")
            st.write(row["summary"])

        # Observations
        if pd.notna(row.get("key_observations")):
            try:
                obs = json.loads(row["key_observations"])
                if obs:
                    st.markdown("### Key Observations")
                    for i, o in enumerate(obs, 1):
                        st.markdown(f"{i}. {o}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Violations
        if pd.notna(row.get("violations")):
            try:
                viols = json.loads(row["violations"])
                if viols:
                    st.markdown("### CFR Violations")
                    st.markdown(cfr_list_to_markdown(viols), unsafe_allow_html=True)
            except (json.JSONDecodeError, TypeError):
                pass

        # Corrective actions
        if pd.notna(row.get("corrective_actions")):
            try:
                actions = json.loads(row["corrective_actions"])
                if actions:
                    st.markdown("### Corrective Actions Required")
                    for a in actions:
                        st.markdown(f"- {a}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Full text
        if pd.notna(row.get("full_text")) and len(str(row["full_text"])) > 50:
            st.markdown("### Full Letter Text")
            st.text_area("", value=str(row["full_text"]), height=400, disabled=True)


# ── Main App ──────────────────────────────────────────────────────────────

def main():
    st.title("🔬 FDA Warning Letter Analysis")
    st.caption("Search, filter, and analyze FDA warning letters for QA insights")

    # Load data
    df = load_data()

    if len(df) == 0:
        st.warning(
            "No data found. Click 'Refresh Data' in the sidebar to fetch warning letters from FDA, "
            "or run `python fetch_fda_data.py` from the command line."
        )
        if st.button("🔄 Fetch Data Now"):
            refresh_data()
        return

    # Sidebar filters
    search_text, years, offices, product_types = render_sidebar(df)
    filtered_df = apply_filters(df, search_text, years, offices, product_types)

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Letters Table",
        "📈 Trends & Visualizations",
        "💡 Insights & Q&A",
        "📄 Letter Detail",
    ])

    with tab1:
        render_letters_table(filtered_df)

    with tab2:
        render_trends(filtered_df)

    with tab3:
        render_insights(df, filtered_df)

    with tab4:
        render_letter_detail(filtered_df)


if __name__ == "__main__":
    main()
