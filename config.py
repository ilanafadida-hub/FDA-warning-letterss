"""
Central configuration for the FDA Warning Letter Analysis System.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
METADATA_CSV = DATA_DIR / "warning_letters.csv"
TEXTS_CSV = DATA_DIR / "letter_texts.csv"
SUMMARIES_CSV = DATA_DIR / "summaries.csv"
STATUS_FILE = DATA_DIR / "last_updated.json"

# ── FDA URLs ───────────────────────────────────────────────────────────────
BASE_URL = "https://www.fda.gov"

# Drupal AJAX endpoint for DataTables (returns structured JSON)
AJAX_URL = f"{BASE_URL}/datatables/views/ajax"
AJAX_PARAMS = {
    "view_name": "warning_letters_solr",
    "view_display_id": "warning_letters_solr_block",
    "_drupal_ajax": "1",
    "_wrapper_format": "drupal_ajax",
}

# Direct XLSX export (bulk metadata download)
XLSX_EXPORT_URL = (
    f"{BASE_URL}/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/warning-letters/datatables-data?_format=xlsx"
)

# ── Request Settings ───────────────────────────────────────────────────────
REQUEST_DELAY = 1.5          # seconds between requests
BATCH_SIZE = 100             # records per AJAX page
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0          # exponential backoff multiplier
REQUEST_TIMEOUT = 30         # seconds

HEADERS = {
    "User-Agent": "FDA-WarningLetter-Research-Tool/1.0 (QA Research)",
    "Accept": "application/json, text/html, */*",
}

# ── OpenAI API ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_TOKENS = 1500
MAX_TEXT_LENGTH = 50000  # truncate letter text before sending to LLM


def ensure_data_dir():
    """Create the data directory if it doesn't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_status():
    """Load the last_updated.json status file."""
    if STATUS_FILE.exists():
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_status(key, **extra):
    """
    Update a key in the status file with current timestamp.

    Example: save_status("metadata_fetch", records=3370, new=15)
    """
    ensure_data_dir()
    status = load_status()
    status[key] = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **extra,
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)
