"""
Full-text extractor for individual FDA warning letter pages.

Fetches each letter's page and extracts clean text content,
reference numbers, product types, and other metadata.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

from config import BASE_URL, HEADERS, REQUEST_DELAY, MAX_RETRIES, RETRY_BACKOFF, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def fetch_letter_page(session, url):
    """
    Fetch the HTML of an individual warning letter page.

    Args:
        session: requests.Session
        url: relative URL path (e.g., /inspections-compliance.../company-name-...)

    Returns:
        raw HTML string, or None on failure
    """
    full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
    # Validate URL points to FDA domain
    from urllib.parse import urlparse
    parsed = urlparse(full_url)
    if parsed.hostname and not parsed.hostname.endswith(".fda.gov"):
        logger.warning(f"Rejected non-FDA URL: {full_url}")
        return None

    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(full_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Letter page not found (404): {full_url}")
                return None
            if e.response.status_code in (429, 500, 502, 503):
                wait = REQUEST_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"HTTP {e.response.status_code} for {full_url}, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = REQUEST_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"Error fetching {full_url}: {e}, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                logger.error(f"Failed to fetch {full_url} after {MAX_RETRIES} attempts: {e}")
                return None

    return None


def extract_letter_text(html):
    """
    Extract structured content from a warning letter HTML page.

    Returns dict with:
        full_text, reference_number, product_type, facility_address, fei_number
    """
    if not html:
        return {
            "full_text": "",
            "reference_number": "",
            "product_type": "",
            "facility_address": "",
            "fei_number": "",
        }

    soup = BeautifulSoup(html, "lxml")

    # Remove navigation, sidebar, footer, scripts
    for tag in soup.find_all(["nav", "footer", "script", "style", "noscript"]):
        tag.decompose()

    # Try multiple selectors for the main content area (handles redesigns)
    content = None
    selectors = [
        "article",
        "div.col-md-8",
        'div[role="main"]',
        "div.field--name-body",
        "main",
        "#content",
    ]
    for sel in selectors:
        content = soup.select_one(sel)
        if content and len(content.get_text(strip=True)) > 200:
            break

    if not content:
        # Fallback: find the largest div by text length
        divs = soup.find_all("div")
        if divs:
            content = max(divs, key=lambda d: len(d.get_text(strip=True)))

    if not content:
        content = soup

    # Extract full text preserving paragraph breaks
    paragraphs = content.find_all(["p", "li", "h2", "h3", "h4"])
    if paragraphs:
        full_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    else:
        full_text = content.get_text(separator="\n", strip=True)

    # Extract reference number (e.g., "320-26-52" or "CMS #XXXXXX")
    ref_match = re.search(r'(?:ref|reference|cms)[#:\s]*(\d[\d\-]+\d)', full_text, re.IGNORECASE)
    reference_number = ref_match.group(1) if ref_match else ""

    # Extract product type from page metadata or content
    product_type = ""
    meta_tags = soup.find_all("meta")
    for meta in meta_tags:
        if meta.get("name", "").lower() in ("category", "product-type"):
            product_type = meta.get("content", "")
            break

    if not product_type:
        # Look for product type in structured content
        product_keywords = {
            "drugs": "Drugs",
            "drug": "Drugs",
            "cgmp": "Drugs/CGMP",
            "device": "Devices",
            "biologic": "Biologics",
            "food": "Food",
            "dietary supplement": "Dietary Supplements",
            "cosmetic": "Cosmetics",
            "tobacco": "Tobacco",
            "veterinary": "Veterinary",
        }
        text_lower = full_text[:2000].lower()
        for keyword, ptype in product_keywords.items():
            if keyword in text_lower:
                product_type = ptype
                break

    # Extract FEI number
    fei_match = re.search(r'FEI[:\s#]*(\d{5,10})', full_text, re.IGNORECASE)
    fei_number = fei_match.group(1) if fei_match else ""

    # Extract facility address (usually near the top, after the recipient)
    facility_address = ""
    lines = full_text.split("\n")
    for i, line in enumerate(lines[:20]):
        # Look for lines that look like addresses (city, state/country patterns)
        if re.search(r'\b[A-Z][a-z]+,?\s+[A-Z]{2}\s+\d{5}', line):
            facility_address = line.strip()
            break
        if re.search(r'\b\d+.*(?:street|avenue|road|blvd|drive|lane|way)\b', line, re.IGNORECASE):
            # Grab this line and possibly the next
            addr_parts = [line.strip()]
            if i + 1 < len(lines) and len(lines[i + 1].strip()) < 100:
                addr_parts.append(lines[i + 1].strip())
            facility_address = ", ".join(addr_parts)
            break

    return {
        "full_text": full_text[:500000],
        "reference_number": reference_number[:50],
        "product_type": product_type[:100],
        "facility_address": facility_address[:300],
        "fei_number": fei_number[:20],
    }


def fetch_and_extract(session, url):
    """Fetch a single letter page and extract its content."""
    html = fetch_letter_page(session, url)
    result = extract_letter_text(html)
    result["url"] = url
    return result


def fetch_and_extract_batch(session, urls, progress_callback=None):
    """
    Fetch and extract text from multiple warning letter pages.

    Args:
        session: requests.Session
        urls: list of relative URLs
        progress_callback: optional callable(current, total)

    Returns:
        list of dicts with extracted content
    """
    results = []

    for i, url in enumerate(urls):
        try:
            result = fetch_and_extract(session, url)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
            results.append({
                "url": url,
                "full_text": "",
                "reference_number": "",
                "product_type": "",
                "facility_address": "",
                "fei_number": "",
            })

        if progress_callback:
            progress_callback(i + 1, len(urls))

        if i < len(urls) - 1:
            time.sleep(REQUEST_DELAY)

    return results
