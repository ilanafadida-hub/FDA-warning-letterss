# FDA Warning Letter Analysis System

A comprehensive tool for Quality Assurance professionals to fetch, analyze, search, and visualize FDA warning letters.

## Features

- **Data Collection**: Automatically fetches all FDA warning letters (metadata + full text)
- **AI Summarization**: Extracts key observations, violations, and corrective actions using Claude API or rule-based patterns
- **Interactive Dashboard**: Streamlit-based Power BI-like interface with search, filters, charts, and Q&A
- **CSV Export**: All data saved locally as CSV files for further analysis in Excel, Power BI, etc.
- **Incremental Updates**: Only fetches new letters on subsequent runs

## Prerequisites

- Python 3.9 or later
- Internet connection (to fetch data from FDA)
- (Optional) Anthropic API key for Claude-powered summarization and Q&A

## Setup

1. **Install Python dependencies:**

```bash
pip install -r requirements.txt
```

2. **(Optional) Configure Claude API:**

Copy `.env.example` to `.env` and add your API key:
```bash
copy .env.example .env
```
Edit `.env` and replace `sk-ant-xxxxx` with your actual key from https://console.anthropic.com/

Without an API key, the system uses rule-based extraction which still works well.

3. **Fetch FDA data:**

```bash
python fetch_fda_data.py
```

This downloads all warning letter metadata and full texts. First run may take 30-60 minutes depending on the number of letters. Subsequent runs only fetch new letters.

Options:
- `--limit 10` — fetch only 10 letters (for testing)
- `--full` — re-fetch all metadata from scratch
- `--texts-only` — only fetch missing full texts

4. **Generate summaries:**

```bash
python summarize_letters.py
```

Options:
- `--method rules` — force rule-based extraction (no API key needed)
- `--method claude` — force Claude API
- `--rescan` — re-summarize all letters
- `--limit 10` — summarize only 10 letters

5. **Launch the dashboard:**

```bash
streamlit run dashboard.py
```

Or simply double-click `run.bat`.

## Dashboard Tabs

### Letters Table
- Searchable, filterable table of all warning letters
- Company names are clickable links to the original FDA warning letter
- Expandable rows showing full details, observations, and letter text
- Export filtered results to CSV

### Trends & Visualizations
- Most common observation keywords (filtered to show only actual findings like contamination, safety, cleaning — not generic terms)
- Top CFR violations cited with clickable links to eCFR
- Common responses by subject

### Insights & Q&A
- Auto-generated insights (year-over-year trends, top themes, repeat offenders)
- Natural language Q&A — ask questions about the data (supports bring-your-own OpenAI API key via sidebar)
- Year-over-year comparison tool
- Key metric cards

### Letter Detail
- Full view of individual letters with all metadata, summary, observations, and complete text

## Data Files

All data is stored in the `data/` folder as CSV files:

| File | Contents |
|------|----------|
| `warning_letters.csv` | Metadata: company, date, office, subject, URL |
| `letter_texts.csv` | Full text of each letter + extracted fields |
| `summaries.csv` | AI/rule-based summaries, observations, violations |

These CSV files can be opened directly in Excel or imported into Power BI for additional analysis.

## Project Structure

```
FDA warning letter/
├── config.py             # Central configuration
├── fetch_fda_data.py     # Data fetching script
├── summarize_letters.py  # Summarization script
├── dashboard.py          # Streamlit dashboard
├── requirements.txt      # Python dependencies
├── .env.example          # API key template
├── run.bat               # Windows launcher
├── README.md             # This file
├── DECISIONS.md          # Architecture decisions
├── PLAN.md               # Project plan
├── data/                 # CSV data files
│   ├── warning_letters.csv
│   ├── letter_texts.csv
│   └── summaries.csv
└── utils/
    ├── scraper.py        # FDA website data fetcher
    ├── parser.py         # Letter text extractor
    └── summarizer.py     # Dual-mode summarization
```
