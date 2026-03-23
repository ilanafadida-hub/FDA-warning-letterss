"""
FDA Warning Letters metadata scraper.

Primary method: AJAX endpoint with proper request headers.
Fallback: XLSX export (no URLs) + HTML scraping for URLs.
"""

import io
import time
import logging
import requests
import pandas as pd
from bs4 import BeautifulSoup

from config import (
    BASE_URL, HEADERS,
    REQUEST_DELAY, BATCH_SIZE, MAX_RETRIES, RETRY_BACKOFF, REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)

LISTING_URL = (
    f"{BASE_URL}/inspections-compliance-enforcement-and-criminal-investigations/"
    "compliance-actions-and-activities/warning-letters"
)
AJAX_URL = f"{BASE_URL}/datatables/views/ajax"


def create_session():
    """Create a requests session with proper headers."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _ajax_request(session, start=0, length=100):
    """
    Make a single AJAX request to the FDA DataTables endpoint.
    Returns dict with 'data', 'recordsTotal', etc.
    """
    data = {
        "view_name": "warning_letter_solr_index",
        "view_display_id": "warning_letter_solr_block",
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "_drupal_ajax": "1",
        "_wrapper_format": "drupal_ajax",
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": LISTING_URL,
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = session.post(AJAX_URL, data=data, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            result = resp.json()

            # Response is either a dict directly or needs extraction
            if isinstance(result, dict) and "data" in result:
                return result
            # Sometimes wrapped in a list
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and "data" in item:
                        return item
            return result

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (429, 500, 502, 503):
                wait = REQUEST_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"HTTP {e.response.status_code}, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = REQUEST_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"Request error: {e}, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"AJAX request failed after {MAX_RETRIES} retries")


def _parse_row(row):
    """
    Parse a single DataTables row (list of HTML fragments) into a dict.

    Columns: [posted_date, letter_date, company+link, issuing_office, subject, ...]
    """
    if not isinstance(row, list) or len(row) < 5:
        return None

    try:
        # Posted date
        soup0 = BeautifulSoup(str(row[0]), "html.parser")
        time_tag0 = soup0.find("time")
        posted_date = time_tag0.get_text(strip=True) if time_tag0 else str(row[0]).strip()

        # Letter issue date
        soup1 = BeautifulSoup(str(row[1]), "html.parser")
        time_tag1 = soup1.find("time")
        letter_date = time_tag1.get_text(strip=True) if time_tag1 else str(row[1]).strip()

        # Company name and URL
        soup2 = BeautifulSoup(str(row[2]), "html.parser")
        link = soup2.find("a")
        if link:
            company = link.get_text(strip=True)
            url = link.get("href", "")
        else:
            company = BeautifulSoup(str(row[2]), "html.parser").get_text(strip=True)
            url = ""

        # Issuing office
        issuing_office = BeautifulSoup(str(row[3]), "html.parser").get_text(strip=True)

        # Subject
        subject = BeautifulSoup(str(row[4]), "html.parser").get_text(separator=" | ", strip=True)

        return {
            "url": url,
            "posted_date": posted_date,
            "letter_date": letter_date,
            "company": company,
            "issuing_office": issuing_office,
            "subject": subject,
        }
    except Exception as e:
        logger.error(f"Error parsing row: {e}")
        return None


def fetch_total_count(session):
    """Fetch total number of warning letters available."""
    result = _ajax_request(session, start=0, length=1)
    if isinstance(result, dict) and "recordsTotal" in result:
        return int(result["recordsTotal"])
    logger.warning("Could not determine total count, defaulting to 5000")
    return 5000


def fetch_metadata_page(session, start, length=BATCH_SIZE):
    """Fetch a single page of warning letter metadata."""
    result = _ajax_request(session, start=start, length=length)

    raw_rows = []
    if isinstance(result, dict) and "data" in result:
        raw_rows = result["data"]

    rows = []
    for raw_row in raw_rows:
        parsed = _parse_row(raw_row)
        if parsed:
            rows.append(parsed)

    return rows


def fetch_all_metadata(session, progress_callback=None, limit=None):
    """
    Fetch all warning letter metadata via AJAX endpoint.

    Args:
        session: requests.Session
        progress_callback: optional callable(current, total)
        limit: optional max number of records to fetch

    Returns:
        list of dicts with warning letter metadata
    """
    total = fetch_total_count(session)
    if limit:
        total = min(total, limit)

    logger.info(f"Fetching metadata for {total} warning letters...")

    all_rows = []
    start = 0

    while start < total:
        length = min(BATCH_SIZE, total - start)
        page_rows = fetch_metadata_page(session, start=start, length=length)
        all_rows.extend(page_rows)

        if progress_callback:
            progress_callback(len(all_rows), total)

        logger.info(f"Fetched {len(all_rows)}/{total} records")
        start += length

        if start < total:
            time.sleep(REQUEST_DELAY)

    return all_rows


def get_new_letters(existing_urls, fresh_rows):
    """
    Filter out letters that are already downloaded.

    Args:
        existing_urls: set of already-known URLs
        fresh_rows: list of dicts from fetch_all_metadata

    Returns:
        list of dicts for new letters only
    """
    return [row for row in fresh_rows if row.get("url", "") not in existing_urls]
