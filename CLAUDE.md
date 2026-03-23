# CLAUDE.md — FDA Warning Letter Analysis System

## Project Overview

A tool for QA professionals to fetch, analyze, search, and visualize FDA warning letters. It scrapes FDA's website for warning letter metadata and full texts, summarizes them using OpenAI GPT or rule-based regex extraction, and presents everything in an interactive Streamlit dashboard.

## Architecture

```
FDA warning letter/
├── config.py              # Central config: paths, URLs, API keys, request settings
├── fetch_fda_data.py      # CLI script — fetches metadata + full text from FDA
├── summarize_letters.py   # CLI script — generates structured summaries (OpenAI or rules)
├── dashboard.py           # Streamlit dashboard (4 tabs: table, trends, insights, detail)
├── api.py                 # FastAPI backend (REST API for letters, analytics, Q&A)
├── run.bat                # Windows launcher for the dashboard
├── Dockerfile.backend     # Docker image for FastAPI service
├── Dockerfile.frontend    # Docker image for Streamlit dashboard
├── railway.json           # Railway deployment config
├── requirements.txt       # Python dependencies
├── .env / .env.example    # OpenAI API key (optional)
├── data/                  # CSV storage (gitignored)
│   ├── warning_letters.csv   # Metadata: company, date, office, subject, URL
│   ├── letter_texts.csv      # Full letter text + extracted fields
│   ├── summaries.csv         # AI/rule-based summaries, observations, violations
│   └── last_updated.json     # Timestamp tracking for incremental updates
└── utils/
    ├── __init__.py
    ├── scraper.py         # FDA AJAX/DataTables endpoint integration + pagination
    ├── parser.py          # Individual letter page fetcher + text/metadata extractor
    └── summarizer.py      # Dual-mode: OpenAI GPT structured extraction + regex fallback
```

## Key Technical Details

- **Data source**: FDA's Drupal AJAX/DataTables endpoint (`/datatables/views/ajax`) returns JSON with HTML fragments per row. Each row is parsed with BeautifulSoup.
- **Incremental updates**: Compares fetched URLs against existing CSVs; only processes new letters.
- **Summarization output schema** (same for both methods): `summary`, `key_observations`, `violations`, `product_types`, `corrective_actions`, `method`. List fields are stored as JSON strings inside CSV cells.
- **AI provider**: OpenAI (`gpt-4o-mini`), configured in `config.py`. Key is read from `OPENAI_API_KEY` env var. Falls back to rule-based regex extraction when no key is set.
- **Rate limiting**: 1.5s delay between FDA requests, exponential backoff on errors, 3 retries max.
- **Security measures**: CSV injection protection (prefix escaping), URL validation (FDA domain only), SSRF prevention in parser, input length truncation for LLM calls.
- **Dashboard** uses Streamlit with Altair charts. CFR citations (e.g., `21 CFR 211.67`) are converted to clickable eCFR links.

## Common Commands

```bash
# Fetch FDA data (incremental)
python fetch_fda_data.py
python fetch_fda_data.py --limit 10    # test with 10 letters
python fetch_fda_data.py --full        # re-fetch all metadata

# Summarize letters
python summarize_letters.py
python summarize_letters.py --method rules   # force rule-based (no API key)
python summarize_letters.py --rescan         # re-summarize all

# Run dashboard
streamlit run dashboard.py

# Run API server
uvicorn api:app --host 0.0.0.0 --port 8000

# Or use the Windows launcher
run.bat
```

## Code Conventions

- Python 3.9+ with type hints used sparingly
- Logging via `logging` module (format: `HH:MM:SS [LEVEL] message`)
- pandas DataFrames for all data manipulation; CSV as storage format
- All list fields (observations, violations, etc.) serialized as JSON strings in CSV
- Atomic file writes for status tracking (`tempfile` + `os.replace`)
- All HTTP requests go through a shared `requests.Session` with custom User-Agent

## Dependencies

requests, beautifulsoup4, lxml, pandas, streamlit, altair, plotly, openai, python-dotenv, openpyxl, fastapi, uvicorn
