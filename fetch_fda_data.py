"""
FDA Warning Letter Data Fetcher.

Downloads warning letter metadata and full texts from the FDA website.
Supports incremental updates — only fetches new letters on subsequent runs.

Usage:
    python fetch_fda_data.py              # incremental update
    python fetch_fda_data.py --full       # re-fetch all metadata
    python fetch_fda_data.py --limit 10   # fetch only 10 letters (testing)
    python fetch_fda_data.py --texts-only # only fetch missing full texts
"""

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from config import METADATA_CSV, TEXTS_CSV, ensure_data_dir, save_status
from utils.scraper import create_session, fetch_all_metadata, get_new_letters
from utils.parser import fetch_and_extract_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


METADATA_DTYPES = {
    "url": str, "posted_date": str, "letter_date": str,
    "company": str, "issuing_office": str, "subject": str,
}

TEXTS_DTYPES = {
    "url": str, "full_text": str, "reference_number": str,
    "product_type": str, "facility_address": str, "fei_number": str, "fetch_date": str,
}


def load_existing_metadata():
    """Load existing metadata CSV, or return empty DataFrame."""
    if METADATA_CSV.exists():
        df = pd.read_csv(METADATA_CSV, dtype=METADATA_DTYPES)
        logger.info(f"Loaded {len(df)} existing metadata records")
        return df
    return pd.DataFrame(columns=list(METADATA_DTYPES.keys()))


def load_existing_texts():
    """Load existing texts CSV, or return empty DataFrame."""
    if TEXTS_CSV.exists():
        df = pd.read_csv(TEXTS_CSV, dtype=TEXTS_DTYPES)
        logger.info(f"Loaded {len(df)} existing letter texts")
        return df
    return pd.DataFrame(columns=list(TEXTS_DTYPES.keys()))


def _sanitize_csv_value(val):
    """Escape values that could be interpreted as formulas in spreadsheet software."""
    if isinstance(val, str) and val and val[0] in ("=", "+", "-", "@"):
        return "'" + val
    return val


def _sanitize_df_for_csv(df):
    """Apply CSV injection protection to all string columns."""
    result = df.copy()
    for col in result.select_dtypes(include=["object"]).columns:
        result[col] = result[col].map(_sanitize_csv_value)
    return result


def save_metadata(df):
    """Save metadata DataFrame to CSV."""
    _sanitize_df_for_csv(df).to_csv(METADATA_CSV, index=False)
    logger.info(f"Saved {len(df)} records to {METADATA_CSV}")


def save_texts(df):
    """Save texts DataFrame to CSV."""
    _sanitize_df_for_csv(df).to_csv(TEXTS_CSV, index=False)
    logger.info(f"Saved {len(df)} records to {TEXTS_CSV}")


def main():
    parser = argparse.ArgumentParser(description="Fetch FDA warning letter data")
    parser.add_argument("--full", action="store_true", help="Re-fetch all metadata (ignore existing)")
    parser.add_argument("--texts-only", action="store_true", help="Only fetch missing full texts")
    parser.add_argument("--limit", type=int, default=None, help="Max number of letters to fetch")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ensure_data_dir()
    session = create_session()

    # ── Step 1: Metadata ──────────────────────────────────────────────
    if not args.texts_only:
        existing_meta = load_existing_metadata() if not args.full else pd.DataFrame()

        print(f"\n[FETCH] Fetching warning letter metadata from FDA...")
        all_rows = fetch_all_metadata(session, limit=args.limit)
        print(f"   Retrieved {len(all_rows)} records from FDA")

        if len(existing_meta) > 0:
            existing_urls = set(existing_meta["url"].tolist())
            new_rows = get_new_letters(existing_urls, all_rows)
            print(f"   {len(new_rows)} new letters found")

            if new_rows:
                new_df = pd.DataFrame(new_rows)
                meta_df = pd.concat([existing_meta, new_df], ignore_index=True)
            else:
                meta_df = existing_meta
        else:
            meta_df = pd.DataFrame(all_rows)
            new_rows = all_rows

        # Remove duplicates by URL
        meta_df = meta_df.drop_duplicates(subset=["url"], keep="last")
        save_metadata(meta_df)

        new_count = len(new_rows) if 'new_rows' in dir() else len(all_rows)
        save_status("metadata_fetch", total_records=len(meta_df), new_records=new_count)
    else:
        meta_df = load_existing_metadata()
        if len(meta_df) == 0:
            print("No metadata found. Run without --texts-only first.")
            sys.exit(1)

    # ── Step 2: Full Texts ────────────────────────────────────────────
    existing_texts = load_existing_texts()
    existing_text_urls = set(existing_texts["url"].tolist()) if len(existing_texts) > 0 else set()

    # Find URLs that need full text fetching
    all_urls = meta_df["url"].tolist()
    missing_urls = [u for u in all_urls if u and isinstance(u, str) and u.strip() and u not in existing_text_urls]

    if args.limit:
        missing_urls = missing_urls[:args.limit]

    SAVE_EVERY = 50  # Save progress every N letters

    if missing_urls:
        print(f"\n[TEXT] Fetching full text for {len(missing_urls)} letters...")

        all_results = []
        today = date.today().isoformat()

        def progress(current, total):
            if current % 10 == 0 or current == total:
                print(f"   Progress: {current}/{total} letters")

        # Fetch in chunks, saving incrementally
        for chunk_start in range(0, len(missing_urls), SAVE_EVERY):
            chunk_urls = missing_urls[chunk_start:chunk_start + SAVE_EVERY]
            chunk_results = fetch_and_extract_batch(session, chunk_urls,
                progress_callback=lambda c, t: progress(chunk_start + c, len(missing_urls)))

            for r in chunk_results:
                r["fetch_date"] = today
            all_results.extend(chunk_results)

            # Save incrementally after each chunk
            new_texts_df = pd.DataFrame(all_results)
            texts_df = pd.concat([existing_texts, new_texts_df], ignore_index=True)
            texts_df = texts_df.drop_duplicates(subset=["url"], keep="last")
            save_texts(texts_df)
            print(f"   [SAVED] {len(texts_df)} total texts to CSV")

        successful = sum(1 for r in all_results if r.get("full_text"))
        failed = len(all_results) - successful
        print(f"   Successfully extracted: {successful}, Failed: {failed}")

        save_status("text_fetch", fetched=successful, failed=failed, total_with_text=len(texts_df))
    else:
        print(f"\n[OK] All letter texts are up to date ({len(existing_texts)} letters)")

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"Data Summary:")
    print(f"   Total letters in metadata: {len(meta_df)}")
    texts_df = load_existing_texts()
    print(f"   Letters with full text:    {len(texts_df)}")
    print(f"   Data saved to: {METADATA_CSV.parent}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
