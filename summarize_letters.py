"""
FDA Warning Letter Summarizer.

Reads downloaded letter texts and generates structured summaries
using OpenAI GPT (preferred) or rule-based extraction (fallback).

Usage:
    python summarize_letters.py                  # summarize new letters
    python summarize_letters.py --method rules   # force rule-based only
    python summarize_letters.py --method openai  # force OpenAI API
    python summarize_letters.py --rescan          # re-summarize all
    python summarize_letters.py --limit 10        # summarize only 10
"""

import argparse
import json
import logging
import sys
import time
from datetime import date

import pandas as pd

from config import TEXTS_CSV, SUMMARIES_CSV, OPENAI_API_KEY, ensure_data_dir, save_status
from utils.summarizer import summarize_letter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_texts():
    """Load letter texts CSV."""
    if not TEXTS_CSV.exists():
        print(f"No letter texts found at {TEXTS_CSV}")
        print("Run fetch_fda_data.py first to download letters.")
        sys.exit(1)
    return pd.read_csv(TEXTS_CSV)


def load_existing_summaries():
    """Load existing summaries CSV, or return empty DataFrame."""
    if SUMMARIES_CSV.exists():
        df = pd.read_csv(SUMMARIES_CSV)
        logger.info(f"Loaded {len(df)} existing summaries")
        return df
    return pd.DataFrame(columns=[
        "url", "summary", "key_observations", "violations",
        "product_types", "corrective_actions", "method", "summarize_date",
    ])


def save_summaries(df):
    """Save summaries DataFrame to CSV."""
    df.to_csv(SUMMARIES_CSV, index=False)
    logger.info(f"Saved {len(df)} summaries to {SUMMARIES_CSV}")


def main():
    parser = argparse.ArgumentParser(description="Summarize FDA warning letters")
    parser.add_argument("--method", choices=["openai", "rules"], default=None,
                        help="Force summarization method (default: auto)")
    parser.add_argument("--rescan", action="store_true", help="Re-summarize all letters")
    parser.add_argument("--limit", type=int, default=None, help="Max letters to summarize")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ensure_data_dir()

    # Load data
    texts_df = load_texts()
    existing_summaries = load_existing_summaries() if not args.rescan else pd.DataFrame()

    # Determine which letters need summarizing
    if len(existing_summaries) > 0:
        summarized_urls = set(existing_summaries["url"].tolist())
        to_summarize = texts_df[~texts_df["url"].isin(summarized_urls)]
    else:
        to_summarize = texts_df
        summarized_urls = set()

    # Filter to letters that have actual text
    to_summarize = to_summarize[to_summarize["full_text"].notna() & (to_summarize["full_text"].str.len() > 50)]

    if args.limit:
        to_summarize = to_summarize.head(args.limit)

    if len(to_summarize) == 0:
        print("[OK] All letters are already summarized.")
        return

    # Determine method
    method = args.method
    if method is None and OPENAI_API_KEY:
        print("[AI] Using OpenAI API for summarization (API key found)")
        method_label = "OpenAI API (with rule-based fallback)"
    elif method == "openai":
        if not OPENAI_API_KEY:
            print("[WARNING] No OPENAI_API_KEY found in .env. Set it or use --method rules")
            sys.exit(1)
        method_label = "OpenAI API"
    else:
        method_label = "Rule-based extraction"
        method = "rules"

    print(f"\n[SUMMARIZE] Summarizing {len(to_summarize)} letters using {method_label}...")

    results = []
    today = date.today().isoformat()
    errors = 0

    for i, (_, row) in enumerate(to_summarize.iterrows()):
        try:
            text = str(row.get("full_text", ""))
            result = summarize_letter(text, method=method)

            # Serialize list fields as JSON strings for CSV storage
            result["url"] = row["url"]
            result["key_observations"] = json.dumps(result.get("key_observations", []))
            result["violations"] = json.dumps(result.get("violations", []))
            result["product_types"] = json.dumps(result.get("product_types", []))
            result["corrective_actions"] = json.dumps(result.get("corrective_actions", []))
            result["summarize_date"] = today

            results.append(result)

            if (i + 1) % 10 == 0 or (i + 1) == len(to_summarize):
                print(f"   Progress: {i + 1}/{len(to_summarize)} letters")

            # Rate limit Claude API calls
            if result.get("method") == "openai":
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error summarizing {row.get('url', '?')}: {e}")
            errors += 1
            continue

    # Combine with existing summaries
    if results:
        new_df = pd.DataFrame(results)
        if len(existing_summaries) > 0:
            all_summaries = pd.concat([existing_summaries, new_df], ignore_index=True)
        else:
            all_summaries = new_df
        all_summaries = all_summaries.drop_duplicates(subset=["url"], keep="last")
        save_summaries(all_summaries)

        save_status("summarization",
                     total_summaries=len(all_summaries),
                     new_summaries=len(results),
                     errors=errors,
                     method=method_label)

    # Summary
    print(f"\n{'='*50}")
    print(f"Summarization Complete:")
    print(f"   Processed:  {len(results)}")
    print(f"   Errors:     {errors}")
    if results:
        methods_used = [r.get("method", "unknown") for r in results]
        openai_count = methods_used.count("openai")
        rules_count = methods_used.count("rule_based")
        print(f"   Via OpenAI: {openai_count}")
        print(f"   Via Rules:  {rules_count}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
