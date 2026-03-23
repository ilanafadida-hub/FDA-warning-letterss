"""
FDA Warning Letter Analysis — Backend API.

FastAPI service that provides endpoints for data fetching,
summarization, search, and analytics.
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io

from config import (
    METADATA_CSV, TEXTS_CSV, SUMMARIES_CSV, DATA_DIR,
    OPENAI_API_KEY, ensure_data_dir, load_status, save_status,
)

app = FastAPI(
    title="FDA Warning Letter API",
    description="API for searching and analyzing FDA warning letters",
    version="1.0.0",
)


# ── Auto-fetch data on startup if empty ───────────────────────────────────

@app.on_event("startup")
async def startup_fetch():
    """Fetch FDA data on first startup if no data exists."""
    import threading
    ensure_data_dir()
    if not METADATA_CSV.exists() or METADATA_CSV.stat().st_size < 100:
        print("[STARTUP] No data found. Fetching FDA warning letters in background...")

        def _fetch_in_background():
            try:
                subprocess.run(
                    [sys.executable, "fetch_fda_data.py", "--limit", "100"],
                    timeout=600, capture_output=True,
                )
                print("[STARTUP] Metadata + texts fetched. Running summarizer...")
                subprocess.run(
                    [sys.executable, "summarize_letters.py"],
                    timeout=300, capture_output=True,
                )
                print("[STARTUP] Data ready!")
            except Exception as e:
                print(f"[STARTUP] Auto-fetch error: {e}")

        thread = threading.Thread(target=_fetch_in_background, daemon=True)
        thread.start()
    else:
        meta = pd.read_csv(METADATA_CSV)
        print(f"[STARTUP] Data loaded: {len(meta)} letters")


# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Data Loading ──────────────────────────────────────────────────────────

def load_metadata():
    if METADATA_CSV.exists():
        return pd.read_csv(METADATA_CSV)
    return pd.DataFrame()


def load_texts():
    if TEXTS_CSV.exists():
        return pd.read_csv(TEXTS_CSV)
    return pd.DataFrame()


def load_summaries():
    if SUMMARIES_CSV.exists():
        return pd.read_csv(SUMMARIES_CSV)
    return pd.DataFrame()


def load_merged():
    """Load and merge all data."""
    meta = load_metadata()
    if len(meta) == 0:
        return pd.DataFrame()

    for col in ["posted_date", "letter_date"]:
        if col in meta.columns:
            meta[col] = pd.to_datetime(meta[col], format="mixed", errors="coerce")

    if "letter_date" in meta.columns:
        meta["year"] = meta["letter_date"].dt.year

    texts = load_texts()
    if len(texts) > 0:
        meta = meta.merge(texts, on="url", how="left", suffixes=("", "_text"))

    summaries = load_summaries()
    if len(summaries) > 0:
        meta = meta.merge(summaries, on="url", how="left", suffixes=("", "_summary"))

    return meta


# ── API Endpoints ─────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "FDA Warning Letter API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/stats")
def stats():
    """Get data statistics."""
    meta = load_metadata()
    texts = load_texts()
    summaries = load_summaries()
    status = load_status()

    return {
        "total_letters": len(meta),
        "letters_with_text": len(texts),
        "letters_with_summaries": len(summaries),
        "last_updated": status,
    }


@app.get("/letters")
def get_letters(
    search: str = Query(None, description="Search text across all fields"),
    year: int = Query(None, description="Filter by year"),
    office: str = Query(None, description="Filter by issuing office"),
    product_type: str = Query(None, description="Filter by product type"),
    limit: int = Query(100, description="Max results"),
    offset: int = Query(0, description="Offset for pagination"),
):
    """Get warning letters with optional filters."""
    df = load_merged()
    if len(df) == 0:
        return {"total": 0, "results": []}

    # Apply filters
    if year and "year" in df.columns:
        df = df[df["year"] == year]

    if office:
        df = df[df["issuing_office"].fillna("").str.contains(office, case=False, na=False)]

    if product_type:
        pt_lower = product_type.lower()
        mask = pd.Series(False, index=df.index)
        for col in ["subject", "product_type", "product_types"]:
            if col in df.columns:
                mask |= df[col].fillna("").str.lower().str.contains(pt_lower, na=False)
        df = df[mask]

    if search:
        search_lower = search.lower()
        mask = pd.Series(False, index=df.index)
        for col in ["company", "subject", "full_text", "summary", "key_observations"]:
            if col in df.columns:
                mask |= df[col].fillna("").str.lower().str.contains(search_lower, na=False)
        df = df[mask]

    total = len(df)

    # Pagination
    df = df.iloc[offset:offset + limit]

    # Convert to records (handle NaN and dates)
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in ["url", "company", "issuing_office", "subject", "summary", "product_type"]:
            val = row.get(col)
            record[col] = str(val) if pd.notna(val) else ""

        for col in ["posted_date", "letter_date"]:
            val = row.get(col)
            record[col] = val.strftime("%Y-%m-%d") if pd.notna(val) else ""

        record["year"] = int(row["year"]) if pd.notna(row.get("year")) else None

        # Parse JSON list fields
        for col in ["key_observations", "violations", "corrective_actions", "product_types"]:
            val = row.get(col)
            if pd.notna(val):
                try:
                    record[col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    record[col] = []
            else:
                record[col] = []

        records.append(record)

    return {"total": total, "results": records}


@app.get("/letter/{url:path}")
def get_letter_detail(url: str):
    """Get full details of a single letter."""
    df = load_merged()
    match = df[df["url"] == url]
    if len(match) == 0:
        # Try partial match
        match = df[df["url"].fillna("").str.contains(url, na=False)]
    if len(match) == 0:
        raise HTTPException(status_code=404, detail="Letter not found")

    row = match.iloc[0]
    result = {}
    for col in row.index:
        val = row[col]
        if pd.isna(val):
            result[col] = None
        elif hasattr(val, "strftime"):
            result[col] = val.strftime("%Y-%m-%d")
        else:
            result[col] = val

    # Parse JSON fields
    for col in ["key_observations", "violations", "corrective_actions", "product_types"]:
        if col in result and result[col]:
            try:
                result[col] = json.loads(result[col])
            except (json.JSONDecodeError, TypeError):
                pass

    return result


@app.get("/analytics")
def get_analytics():
    """Get analytics data for charts."""
    df = load_merged()
    if len(df) == 0:
        return {}

    result = {}

    # Letters by year
    if "year" in df.columns:
        yearly = df.groupby("year").size().to_dict()
        result["by_year"] = {str(int(k)): v for k, v in yearly.items() if pd.notna(k)}

    # By office
    if "issuing_office" in df.columns:
        result["by_office"] = df["issuing_office"].value_counts().head(10).to_dict()

    # Top violations
    if "violations" in df.columns:
        all_v = []
        for v in df["violations"].dropna():
            try:
                all_v.extend(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                pass
        result["top_violations"] = dict(Counter(all_v).most_common(15))

    # Top observation themes
    if "key_observations" in df.columns:
        themes = {"cleaning": 0, "data integrity": 0, "validation": 0, "contamination": 0,
                  "documentation": 0, "training": 0, "sterility": 0, "labeling": 0}
        for obs_json in df["key_observations"].dropna():
            try:
                obs_text = " ".join(json.loads(obs_json)).lower()
                for theme in themes:
                    if theme in obs_text:
                        themes[theme] += 1
            except (json.JSONDecodeError, TypeError):
                pass
        result["observation_themes"] = {k: v for k, v in themes.items() if v > 0}

    # Repeat offenders
    if "company" in df.columns:
        company_counts = df["company"].value_counts()
        repeaters = company_counts[company_counts > 1].head(10).to_dict()
        result["repeat_offenders"] = repeaters

    return result


@app.get("/offices")
def get_offices():
    """Get list of unique issuing offices."""
    df = load_metadata()
    if "issuing_office" in df.columns:
        return sorted(df["issuing_office"].dropna().unique().tolist())
    return []


@app.get("/years")
def get_years():
    """Get list of available years."""
    df = load_metadata()
    if "letter_date" in df.columns:
        dates = pd.to_datetime(df["letter_date"], format="mixed", errors="coerce")
        years = sorted(dates.dt.year.dropna().unique().astype(int).tolist(), reverse=True)
        return years
    return []


@app.post("/refresh")
def refresh_data():
    """Trigger data refresh (fetch new letters + summarize)."""
    try:
        result = subprocess.run(
            [sys.executable, "fetch_fda_data.py"],
            capture_output=True, text=True, timeout=600,
        )
        fetch_output = result.stdout + result.stderr

        result2 = subprocess.run(
            [sys.executable, "summarize_letters.py"],
            capture_output=True, text=True, timeout=300,
        )
        summarize_output = result2.stdout + result2.stderr

        return {
            "status": "ok",
            "fetch": fetch_output[-500:],
            "summarize": summarize_output[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Data refresh timed out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export")
def export_csv(
    search: str = Query(None),
    year: int = Query(None),
    office: str = Query(None),
):
    """Export filtered data as CSV download."""
    letters = get_letters(search=search, year=year, office=office, limit=10000)
    df = pd.DataFrame(letters["results"])
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fda_warning_letters.csv"},
    )


@app.post("/ask")
def ask_question(question: str = Query(..., description="Your question about the data")):
    """Answer a question about the data using OpenAI or rule-based analysis."""
    df = load_merged()

    # Try OpenAI
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)

            # Build context
            context_lines = [f"Dataset: {len(df)} FDA warning letters"]
            if "year" in df.columns:
                context_lines.append(f"Years: {df['year'].dropna().astype(int).to_dict()}")
            if "issuing_office" in df.columns:
                context_lines.append(f"Top offices: {df['issuing_office'].value_counts().head(5).to_dict()}")

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1000,
                messages=[
                    {"role": "system", "content": "You are an FDA regulatory data analyst. Answer concisely."},
                    {"role": "user", "content": f"Data:\n{chr(10).join(context_lines)}\n\nQuestion: {question}"},
                ],
            )
            return {"answer": response.choices[0].message.content, "method": "openai"}
        except Exception as e:
            pass

    # Fallback: basic stats
    return {
        "answer": f"Based on {len(df)} letters in the dataset. Add OPENAI_API_KEY for AI-powered answers.",
        "method": "rule_based",
    }


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
