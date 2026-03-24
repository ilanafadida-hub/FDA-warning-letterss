"""
FDA Warning Letter Analysis Dashboard.

Interactive Streamlit app for searching, filtering, visualizing,
and analyzing FDA warning letters.

Run with: streamlit run dashboard.py
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

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

# ── Global Custom Styling ─────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Bold section headers ── */
.section-header {
    font-size: 1.4rem;
    font-weight: 800;
    color: #1B3A5C;
    border-left: 5px solid #2196F3;
    padding: 8px 0 8px 14px;
    margin: 1.5rem 0 1rem 0;
    letter-spacing: 0.3px;
}
.section-header-red {
    font-size: 1.4rem;
    font-weight: 800;
    color: #8B1A1A;
    border-left: 5px solid #E53935;
    padding: 8px 0 8px 14px;
    margin: 1.5rem 0 1rem 0;
}
.section-header-green {
    font-size: 1.4rem;
    font-weight: 800;
    color: #1B5E20;
    border-left: 5px solid #43A047;
    padding: 8px 0 8px 14px;
    margin: 1.5rem 0 1rem 0;
}
.section-header-purple {
    font-size: 1.4rem;
    font-weight: 800;
    color: #4A148C;
    border-left: 5px solid #7E57C2;
    padding: 8px 0 8px 14px;
    margin: 1.5rem 0 1rem 0;
}
.section-header-orange {
    font-size: 1.4rem;
    font-weight: 800;
    color: #BF360C;
    border-left: 5px solid #FF7043;
    padding: 8px 0 8px 14px;
    margin: 1.5rem 0 1rem 0;
}

/* ── Colored dividers between sections ── */
.divider-blue { border: none; height: 3px; background: linear-gradient(90deg, #2196F3 0%, transparent 100%); margin: 1.8rem 0; }
.divider-red { border: none; height: 3px; background: linear-gradient(90deg, #E53935 0%, transparent 100%); margin: 1.8rem 0; }
.divider-green { border: none; height: 3px; background: linear-gradient(90deg, #43A047 0%, transparent 100%); margin: 1.8rem 0; }
.divider-purple { border: none; height: 3px; background: linear-gradient(90deg, #7E57C2 0%, transparent 100%); margin: 1.8rem 0; }
.divider-orange { border: none; height: 3px; background: linear-gradient(90deg, #FF7043 0%, transparent 100%); margin: 1.8rem 0; }
.divider-rainbow {
    border: none; height: 4px; margin: 2rem 0;
    background: linear-gradient(90deg, #2196F3, #7E57C2, #E53935, #FF7043, #43A047);
    border-radius: 2px;
}

/* ── Metric cards ── */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #f8f9ff 0%, #eef2ff 100%);
    border: 1px solid #c5cae9;
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}
div[data-testid="stMetric"] label {
    font-weight: 700 !important;
    color: #1B3A5C !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: #0D47A1 !important;
}

/* ── Tab styling ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 3px solid #e3e8f0;
}
.stTabs [data-baseweb="tab"] {
    font-weight: 700;
    font-size: 1rem;
    padding: 10px 20px;
    border-radius: 8px 8px 0 0;
    color: #37474F;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #1976D2, #1565C0) !important;
    color: white !important;
    font-weight: 800;
    border-bottom: 3px solid #0D47A1;
}

/* ── Expander styling ── */
.streamlit-expanderHeader {
    font-weight: 700 !important;
    color: #1B3A5C !important;
    font-size: 1rem !important;
    background-color: #f0f4ff !important;
    border-radius: 6px !important;
}

/* ── Title bar ── */
h1 {
    color: #0D47A1 !important;
    font-weight: 900 !important;
    letter-spacing: -0.5px;
}

/* ── Sidebar title ── */
.css-1d391kg h1, [data-testid="stSidebar"] h1 {
    color: #1565C0 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f5f7ff 0%, #e8ecf4 100%);
}

/* ── Info card style ── */
.info-card {
    background: #f8f9ff;
    border: 1px solid #c5cae9;
    border-radius: 10px;
    padding: 16px 20px;
    margin: 10px 0;
}
.info-card-green {
    background: #f1f8e9;
    border: 1px solid #a5d6a7;
    border-radius: 10px;
    padding: 16px 20px;
    margin: 10px 0;
}
.info-card-orange {
    background: #fff3e0;
    border: 1px solid #ffcc80;
    border-radius: 10px;
    padding: 16px 20px;
    margin: 10px 0;
}
.info-card-red {
    background: #fce4ec;
    border: 1px solid #ef9a9a;
    border-radius: 10px;
    padding: 16px 20px;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# ── User API Key Input ────────────────────────────────────────────────────
with st.sidebar:
    user_api_key = st.text_input(
        "🔑 OpenAI API Key (optional)",
        type="password",
        help="Enter your own OpenAI API key to enable AI-powered Q&A and summaries. "
             "Without a key, the system uses rule-based analysis (still works well).",
        placeholder="sk-..."
    )
    if user_api_key:
        st.success("API key set for this session")
    else:
        st.info("No API key → rule-based analysis")


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
        # Sanitize: escape markdown special chars in unparseable citations
        safe = citation.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")
        return safe

    part = m.group(1)
    section = m.group(2)
    # Sanitize remainder: only allow parenthesized subsections like (a)(1)
    raw_remainder = m.group(3).strip() if m.group(3) else ""
    remainder = re.match(r'^(\([a-zA-Z0-9]+\))*', raw_remainder).group(0) if raw_remainder else ""

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
                mask |= filtered["subject"].fillna("").str.lower().str.contains(pt_lower, na=False, regex=False)
            if "product_type" in filtered.columns:
                mask |= filtered["product_type"].fillna("").str.lower().str.contains(pt_lower, na=False, regex=False)
            if "product_types" in filtered.columns:
                mask |= filtered["product_types"].fillna("").str.lower().str.contains(pt_lower, na=False, regex=False)
        filtered = filtered[mask]

    # Text search (across multiple columns)
    if search_text:
        search_lower = search_text.lower()
        text_cols = ["company", "subject", "full_text", "summary", "key_observations"]
        mask = pd.Series(False, index=filtered.index)
        for col in text_cols:
            if col in filtered.columns:
                mask |= filtered[col].fillna("").str.lower().str.contains(search_lower, na=False, regex=False)
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
        # Rate limit: prevent rapid repeated clicks
        last_refresh = st.session_state.get("_last_refresh_time")
        now = datetime.now()
        if last_refresh and (now - last_refresh).total_seconds() < 60:
            st.sidebar.warning("Please wait at least 60 seconds between refreshes.")
        else:
            st.session_state["_last_refresh_time"] = now
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
            script_dir = str(Path(__file__).parent)
            subprocess.run([sys.executable, os.path.join(script_dir, "fetch_fda_data.py")], check=True, capture_output=True)
            st.success("Data fetched successfully!")
        except subprocess.CalledProcessError as e:
            st.error("Data fetch failed. Check the console log for details.")
            return

    with st.spinner("Summarizing new letters..."):
        try:
            subprocess.run([sys.executable, os.path.join(script_dir, "summarize_letters.py")], check=True, capture_output=True)
            st.success("Summarization complete!")
        except subprocess.CalledProcessError as e:
            st.error("Summarization failed. Check the console log for details.")

    st.cache_data.clear()
    st.rerun()


# ── Tab 1: Letters Table ──────────────────────────────────────────────────

def render_letters_table(filtered_df):
    """Render the searchable letters table."""
    st.markdown(f'<div class="section-header">📋 Warning Letters ({len(filtered_df)} results)</div>', unsafe_allow_html=True)

    if len(filtered_df) == 0:
        st.info("No letters match your filters. Try broadening your search.")
        return

    # Display columns
    display_cols = ["letter_date", "company", "issuing_office", "subject"]
    if "summary" in filtered_df.columns:
        display_cols.append("summary")

    display_df = filtered_df[
        [c for c in display_cols + ["url"] if c in filtered_df.columns]
    ].copy()

    # Format date
    if "letter_date" in display_df.columns:
        display_df["letter_date"] = display_df["letter_date"].dt.strftime("%Y-%m-%d")

    # Build HTML table with clickable company links
    has_url = "url" in display_df.columns
    header_cols = ["Date", "Company", "Issuing Office", "Subject"]
    if "summary" in display_df.columns:
        header_cols.append("Summary")

    table_html = """<style>
    .letters-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .letters-table th { background-color: #f0f2f6; padding: 10px 12px; text-align: left; border-bottom: 2px solid #ddd; position: sticky; top: 0; }
    .letters-table td { padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }
    .letters-table tr:hover { background-color: #f8f9fb; }
    .letters-table a { color: #1a73e8; text-decoration: none; font-weight: 500; }
    .letters-table a:hover { text-decoration: underline; }
    .letters-table .summary-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>"""
    table_html += '<div style="max-height: 500px; overflow-y: auto;"><table class="letters-table"><thead><tr>'
    for col in header_cols:
        table_html += f"<th>{col}</th>"
    table_html += "</tr></thead><tbody>"

    for _, row in display_df.iterrows():
        table_html += "<tr>"
        # Date
        table_html += f'<td style="white-space: nowrap;">{row.get("letter_date", "N/A")}</td>'
        # Company — clickable link to FDA letter
        company = str(row.get("company", "Unknown")).replace("<", "&lt;").replace(">", "&gt;")
        if has_url and pd.notna(row.get("url")):
            url = str(row["url"]).replace('"', "&quot;")
            table_html += f'<td><a href="{url}" target="_blank">{company}</a></td>'
        else:
            table_html += f"<td>{company}</td>"
        # Issuing Office
        office = str(row.get("issuing_office", "N/A")).replace("<", "&lt;").replace(">", "&gt;")
        table_html += f"<td>{office}</td>"
        # Subject
        subject = str(row.get("subject", "N/A")).replace("<", "&lt;").replace(">", "&gt;")
        table_html += f"<td>{subject}</td>"
        # Summary
        if "summary" in display_df.columns:
            summary = str(row.get("summary", "")).replace("<", "&lt;").replace(">", "&gt;") if pd.notna(row.get("summary")) else ""
            table_html += f'<td class="summary-cell" title="{summary}">{summary[:120]}{"..." if len(summary) > 120 else ""}</td>'
        table_html += "</tr>"

    table_html += "</tbody></table></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    # Drop url from export
    export_df = display_df.drop(columns=["url"], errors="ignore")
    col_names = {
        "letter_date": "Date",
        "company": "Company",
        "issuing_office": "Issuing Office",
        "subject": "Subject",
        "summary": "Summary",
    }
    export_df = export_df.rename(columns=col_names)

    # Export button
    csv_data = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Export filtered results to CSV",
        csv_data,
        file_name="fda_warning_letters_filtered.csv",
        mime="text/csv",
    )

    # Expandable letter details
    st.markdown('<hr class="divider-blue">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📄 Letter Details</div>', unsafe_allow_html=True)

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
                        st.markdown(cfr_list_to_markdown(viols), unsafe_allow_html=False)
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
    st.markdown('<div class="section-header-purple">📈 Trends & Visualizations</div>', unsafe_allow_html=True)

    if len(filtered_df) == 0:
        st.info("No data to visualize. Try broadening your filters.")
        return

    # ── Top Finding Categories (curated QA topic analysis) ──
    if "key_observations" in filtered_df.columns:
        st.markdown('<div class="section-header-purple" style="font-size:1.15rem;">🔎 Top Finding Categories</div>', unsafe_allow_html=True)
        _FINDING_TOPICS = [
            ("Contamination", ["contamination", "contaminated", "cross-contamination", "cross contamination"]),
            ("Cleaning / Sanitation", ["cleaning", "sanitization", "sanitation", "sanitizing", "insanitary", "unsanitary"]),
            ("Sterility / Aseptic Processing", ["sterility", "sterile", "aseptic", "sterilization", "sterilized"]),
            ("Microbiological Controls", ["microbial", "microbiological", "microorganism", "bioburden", "endotoxin", "bacterial"]),
            ("HACCP / Hazard Analysis", ["haccp", "hazard analysis", "critical control point", "preventive controls"]),
            ("Stability / Expiration", ["stability", "expiration", "shelf life", "degradation"]),
            ("Laboratory Controls", ["laboratory", "lab controls", "out-of-specification", "oos", "out of specification"]),
            ("Process Validation", ["process validation", "cleaning validation", "method validation", "validated"]),
            ("Analysis Intervals", ["intervals", "frequency of analysis", "periodic testing", "annual review"]),
            ("Supplier / Vendor Controls", ["supplier", "suppliers", "vendor", "vendor qualification", "incoming"]),
            ("CAPA / Root Cause", ["capa", "corrective action", "preventive action", "root cause"]),
            ("Complaint Handling", ["complaint", "complaints", "adverse event", "adverse reaction"]),
            ("Water Systems", ["water system", "purified water", "water for injection", "wfi"]),
            ("Equipment / Calibration", ["maintenance", "calibration", "equipment qualification"]),
            ("Labeling / Misbranding", ["mislabel", "misbranded", "misbranding", "labeling violation", "false label"]),
            ("Adulteration", ["adulterated", "adulteration", "unapproved"]),
            ("Pest Control", ["pest", "rodent", "insect", "vermin", "infestation"]),
            ("Temperature Control", ["temperature", "cold chain", "refrigeration", "temperature control"]),
            ("Change Control", ["change control", "change management", "uncontrolled change"]),
            ("Training Gaps", ["training", "untrained", "inadequate training"]),
            ("Raw Materials / Ingredients", ["raw material", "active ingredient", "ingredient identity", "excipient"]),
            ("Recall / Batch Failure", ["recall", "batch failure", "market withdrawal", "rejected"]),
            ("Foreign Material", ["foreign material", "foreign matter", "particulate", "particle"]),
            ("Packaging / Closure Integrity", ["packaging", "closure", "container closure", "seal integrity"]),
            ("Environmental Monitoring", ["environmental monitoring", "cleanroom", "clean room", "air quality"]),
            ("Data Integrity", ["data integrity", "audit trail", "falsified", "manipulated", "backdating"]),
            ("Deviation Management", ["deviation", "non-conformance", "nonconformance", "out-of-trend"]),
            ("Risk Assessment", ["risk assessment", "risk analysis", "risk management"]),
            ("Allergen Control", ["allergen", "allergens", "undeclared"]),
            ("Drug Impurities / Potency", ["impurity", "impurities", "dissolution", "potency", "content uniformity"]),
        ]
        topic_counts = Counter()
        for obs_json in filtered_df["key_observations"].dropna():
            try:
                for obs in json.loads(obs_json):
                    text = obs.lower()
                    for display_label, patterns in _FINDING_TOPICS:
                        if any(pat in text for pat in patterns):
                            topic_counts[display_label] += 1
                            break
            except (json.JSONDecodeError, TypeError):
                pass

        if topic_counts:
            topic_data = topic_counts.most_common(30)
            max_count = topic_data[0][1] if topic_data else 1

            # Color palette for rows (cycles through)
            _row_colors = [
                ("#7E57C2", "#f3e5f5"),  # purple
                ("#2196F3", "#e3f2fd"),  # blue
                ("#43A047", "#e8f5e9"),  # green
                ("#FF7043", "#fff3e0"),  # orange
                ("#E53935", "#fce4ec"),  # red
                ("#00897B", "#e0f2f1"),  # teal
            ]

            table_html = """<style>
            .findings-table { width: 100%; border-collapse: separate; border-spacing: 0 6px; font-size: 15px; }
            .findings-table td { padding: 10px 16px; }
            .findings-row { border-radius: 8px; transition: transform 0.15s; }
            .findings-row:hover { transform: scale(1.01); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .findings-category { font-weight: 700; color: #1B3A5C; width: 45%; }
            .findings-bar-cell { width: 40%; }
            .findings-bar-bg { background: #e0e0e0; border-radius: 6px; height: 22px; overflow: hidden; }
            .findings-bar { height: 100%; border-radius: 6px; transition: width 0.5s; }
            .findings-count { font-weight: 800; font-size: 1.1rem; text-align: right; width: 15%; white-space: nowrap; }
            </style>"""
            table_html += '<table class="findings-table">'
            for i, (category, count) in enumerate(topic_data):
                bar_color, bg_color = _row_colors[i % len(_row_colors)]
                pct = (count / max_count) * 100
                table_html += f"""<tr class="findings-row" style="background:{bg_color};">
                    <td class="findings-category">{category}</td>
                    <td class="findings-bar-cell">
                        <div class="findings-bar-bg">
                            <div class="findings-bar" style="width:{pct:.0f}%; background:{bar_color};"></div>
                        </div>
                    </td>
                    <td class="findings-count" style="color:{bar_color};">{count}</td>
                </tr>"""
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)

    # ── Top Violations ──
    if "violations" in filtered_df.columns:
        st.markdown('<hr class="divider-red">', unsafe_allow_html=True)
        st.markdown('<div class="section-header-red" style="font-size:1.15rem;">⚠️ Top CFR Violations Cited</div>', unsafe_allow_html=True)
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
            st.markdown("**🔗 Click to view regulation:**")
            st.markdown(cfr_list_to_markdown([v for v, _ in viol_counts[:10]]), unsafe_allow_html=False)

    # ── Common Responses by Subject ──
    if "subject" in filtered_df.columns:
        st.markdown('<hr class="divider-green">', unsafe_allow_html=True)
        st.markdown('<div class="section-header-green" style="font-size:1.15rem;">🏷️ Common Responses by Subject</div>', unsafe_allow_html=True)
        subject_counts = filtered_df["subject"].dropna().value_counts().head(15).reset_index()
        subject_counts.columns = ["subject", "count"]
        if len(subject_counts) > 0:
            import plotly.express as px
            fig = px.pie(
                subject_counts,
                values="count",
                names="subject",
                hole=0.35,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate="<b>%{label}</b><br>Letters: %{value}<br>Share: %{percent}<extra></extra>",
            )
            fig.update_layout(
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.02,
                    font=dict(size=12),
                ),
                height=500,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Tab 3: Insights & Q&A ────────────────────────────────────────────────

def render_insights(df, filtered_df):
    """Render insights, metrics, and Q&A interface."""
    st.markdown('<div class="section-header-orange">💡 Insights & Q&A</div>', unsafe_allow_html=True)

    if len(df) == 0:
        st.info("No data available. Fetch data first using the Refresh button.")
        return

    # ── Q&A Chat Interface (placed first for easy access) ──
    st.markdown('<div class="section-header" style="font-size:1.15rem;">💬 Ask a Question About the Data</div>', unsafe_allow_html=True)
    st.caption("Ask questions like: 'Which companies received multiple warning letters?', "
               "'What are the most common violations in 2024?', 'Show trends in cleaning observations'")
    if not (user_api_key or OPENAI_API_KEY):
        st.caption("💡 Enter your OpenAI API key in the sidebar to enable AI-powered answers")

    user_question = st.text_input("Your question:", placeholder="e.g., What are the top violations in food safety?")

    if user_question:
        answer = answer_question(user_question, df, filtered_df)
        st.markdown("**Answer:**")
        st.write(answer)

    st.markdown('<hr class="divider-orange">', unsafe_allow_html=True)

    # ── Key Metrics Cards ──
    st.markdown('<div class="section-header-orange" style="font-size:1.15rem;">📊 Key Metrics</div>', unsafe_allow_html=True)
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

    st.markdown('<hr class="divider-green">', unsafe_allow_html=True)

    # ── Auto-Generated Insights ──
    st.markdown('<div class="section-header-green" style="font-size:1.15rem;">🧠 Auto-Generated Insights</div>', unsafe_allow_html=True)

    insights = generate_insights(df)
    for insight in insights:
        st.markdown(f'<div class="info-card">💡 <strong>{insight}</strong></div>', unsafe_allow_html=True)

    st.markdown('<hr class="divider-blue">', unsafe_allow_html=True)

    # ── Year-over-Year Comparison ──
    st.markdown('<div class="section-header" style="font-size:1.15rem;">📅 Compare Two Years</div>', unsafe_allow_html=True)
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

    st.markdown('<hr class="divider-purple">', unsafe_allow_html=True)

    # ── Observations & Responses Review ──
    render_observations_and_responses(filtered_df)

    st.markdown('<hr class="divider-rainbow">', unsafe_allow_html=True)

    # ── Acceptable Responses Reference ──
    render_acceptable_responses()



def render_observations_and_responses(df):
    """Show paired observations and corrective actions from letters."""
    st.markdown('<div class="section-header-red" style="font-size:1.15rem;">🔬 Observations & Responses Review</div>', unsafe_allow_html=True)
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
                    st.markdown(cfr_list_to_markdown(p["violations"][:5]), unsafe_allow_html=False)

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
    st.markdown('<div class="section-header-green" style="font-size:1.15rem;">✅ Acceptable Response Reference Guide</div>', unsafe_allow_html=True)
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
        st.markdown(cfr_list_to_markdown(info["key_regulations"]), unsafe_allow_html=False)

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

    # Try OpenAI API first (user's key takes priority over server key)
    active_key = user_api_key or OPENAI_API_KEY
    if active_key:
        try:
            return _answer_with_openai(question, filtered_df, api_key=active_key)
        except Exception:
            st.warning("AI-powered Q&A unavailable. Using statistical analysis instead.")

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
    result += f"\nFor more detailed answers, enter your OpenAI API key in the sidebar."
    return result


def _answer_with_openai(question, df, api_key=None):
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

    client = OpenAI(api_key=api_key or OPENAI_API_KEY)
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
    st.markdown('<div class="section-header">📄 Letter Detail View</div>', unsafe_allow_html=True)

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
        st.markdown('<div class="section-header" style="font-size:1.15rem;">📋 Metadata</div>', unsafe_allow_html=True)
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
            st.markdown('<hr class="divider-blue">', unsafe_allow_html=True)
            st.markdown('<div class="section-header-green" style="font-size:1.15rem;">📝 Summary</div>', unsafe_allow_html=True)
            st.write(row["summary"])

        # Observations
        if pd.notna(row.get("key_observations")):
            try:
                obs = json.loads(row["key_observations"])
                if obs:
                    st.markdown('<hr class="divider-orange">', unsafe_allow_html=True)
                    st.markdown('<div class="section-header-orange" style="font-size:1.15rem;">🔍 Key Observations</div>', unsafe_allow_html=True)
                    for i, o in enumerate(obs, 1):
                        st.markdown(f"{i}. {o}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Violations
        if pd.notna(row.get("violations")):
            try:
                viols = json.loads(row["violations"])
                if viols:
                    st.markdown('<hr class="divider-red">', unsafe_allow_html=True)
                    st.markdown('<div class="section-header-red" style="font-size:1.15rem;">⚠️ CFR Violations</div>', unsafe_allow_html=True)
                    st.markdown(cfr_list_to_markdown(viols), unsafe_allow_html=False)
            except (json.JSONDecodeError, TypeError):
                pass

        # Corrective actions
        if pd.notna(row.get("corrective_actions")):
            try:
                actions = json.loads(row["corrective_actions"])
                if actions:
                    st.markdown('<hr class="divider-green">', unsafe_allow_html=True)
                    st.markdown('<div class="section-header-green" style="font-size:1.15rem;">✅ Corrective Actions Required</div>', unsafe_allow_html=True)
                    for a in actions:
                        st.markdown(f"- {a}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Full text
        if pd.notna(row.get("full_text")) and len(str(row["full_text"])) > 50:
            st.markdown('<hr class="divider-purple">', unsafe_allow_html=True)
            st.markdown('<div class="section-header-purple" style="font-size:1.15rem;">📜 Full Letter Text</div>', unsafe_allow_html=True)
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
