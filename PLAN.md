# FDA Warning Letter Analysis System — Project Plan

## Purpose
Build a tool for QA professionals to fetch, analyze, and search all FDA warning letters. The system provides a searchable, filterable dashboard similar to Power BI where users can find specific observations (e.g., "cleaning") across all letters.

## Architecture

```
FDA warning letter/
├── config.py             # Central configuration
├── fetch_fda_data.py     # Data fetching orchestrator
├── summarize_letters.py  # Summarization orchestrator
├── dashboard.py          # Streamlit dashboard (4 tabs)
├── data/                 # CSV storage
│   ├── warning_letters.csv   # Metadata
│   ├── letter_texts.csv      # Full letter text
│   └── summaries.csv         # AI/rule-based summaries
└── utils/
    ├── scraper.py        # FDA AJAX metadata fetcher
    ├── parser.py         # Letter text extractor
    └── summarizer.py     # Claude API + rule-based summarizer
```

## Implementation Steps

### Step 1: Project Scaffolding (DONE)
- [x] config.py — URLs, paths, constants
- [x] requirements.txt — all dependencies
- [x] .env.example — API key template
- [x] .gitignore
- [x] utils/__init__.py

### Step 2: FDA Metadata Scraper (DONE)
- [x] utils/scraper.py — AJAX endpoint integration
- [x] Pagination with start/length params
- [x] HTML fragment parsing in JSON response
- [x] Incremental update support

### Step 3: Full-Text Extractor (DONE)
- [x] utils/parser.py — individual letter page fetcher
- [x] Multiple CSS selector fallbacks
- [x] Extracts: full_text, reference_number, product_type, facility_address, fei_number

### Step 4: Summarizer (DONE)
- [x] utils/summarizer.py — dual-mode engine
- [x] Claude API mode with structured JSON extraction
- [x] Rule-based fallback with regex patterns
- [x] Auto-fallback behavior

### Step 5: Fetch Orchestrator (DONE)
- [x] fetch_fda_data.py — CLI with argparse
- [x] Incremental updates
- [x] Progress reporting

### Step 6: Summarize Orchestrator (DONE)
- [x] summarize_letters.py — CLI with argparse
- [x] Batch processing with progress

### Step 7: Streamlit Dashboard (DONE)
- [x] Tab 1: Letters Table — searchable, filterable, expandable, CSV export
- [x] Tab 2: Trends & Visualizations — charts, heatmaps, trend analysis
- [x] Tab 3: Insights & Q&A — auto-insights, metrics, comparison, chat interface
- [x] Tab 4: Letter Detail — full single-letter view

### Step 8: Documentation (DONE)
- [x] README.md — setup and usage guide
- [x] DECISIONS.md — architecture decisions log
- [x] PLAN.md — this file
- [x] run.bat — Windows launcher

## Data Flow

```
FDA Website ──(AJAX)──> scraper.py ──> warning_letters.csv (metadata)
                  │
                  └──(HTTP)──> parser.py ──> letter_texts.csv (full text)
                                    │
                                    └──> summarizer.py ──> summaries.csv (analysis)
                                              │
                                              └──> dashboard.py (Streamlit UI)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Data fetching | requests + BeautifulSoup |
| Data storage | pandas + CSV |
| AI summarization | Claude API (Sonnet) |
| Rule-based extraction | regex patterns |
| Dashboard | Streamlit + Altair |
| Configuration | python-dotenv |

## Verification Checklist

1. `python fetch_fda_data.py --limit 5` — creates CSVs with 5 letters
2. `python summarize_letters.py --limit 5` — creates summaries
3. `streamlit run dashboard.py` — dashboard loads and all tabs work
4. Search "cleaning" — returns relevant observations
5. Export filtered results — CSV downloads correctly
6. Refresh button — fetches new data and updates display
