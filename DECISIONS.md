# Architecture Decisions Log

## Decision 1: FDA Data Source — AJAX Endpoint over HTML Scraping

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Need to fetch FDA warning letter metadata. Options: scrape HTML tables, use openFDA API, or use the Drupal AJAX endpoint.

**Decision:** Use the FDA website's internal Drupal AJAX/DataTables endpoint (`/datatables/views/ajax`) which returns structured JSON.

**Rationale:**
- The openFDA API does NOT have a dedicated warning letters endpoint
- HTML scraping is fragile and breaks when the page layout changes
- The AJAX endpoint returns clean JSON with pagination support
- This is the same endpoint the website itself uses for its tables

**Risk:** FDA could change the AJAX endpoint parameters. Mitigation: the XLSX export URL serves as a fallback for bulk metadata.

---

## Decision 2: Dual-Mode Summarization (Claude API + Rule-Based)

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Need to extract observations, violations, and corrective actions from each letter.

**Decision:** Support both Claude API summarization (higher quality) and rule-based regex extraction (free, no API key needed).

**Rationale:**
- Claude API produces much better structured summaries but requires a paid API key
- Rule-based extraction is free and works offline
- Auto-fallback: tries Claude if API key is available, falls back to rules
- Same output schema for both methods enables consistent dashboard display

**Cost estimate:** ~$5-15 to summarize the full FDA warning letter corpus with Claude Sonnet.

---

## Decision 3: Local CSV Storage

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Need to store fetched data persistently.

**Decision:** Use CSV files in a local `data/` folder.

**Rationale:**
- No database setup required
- CSV files can be opened directly in Excel or imported into Power BI
- pandas reads/writes CSV natively
- Suitable for the expected data volume (thousands of letters, not millions)
- Users specifically requested CSV access for external analysis

**Trade-off:** JSON list fields (observations, violations) are stored as JSON strings inside CSV cells. This is slightly awkward but keeps the flat-file approach simple.

---

## Decision 4: Streamlit for Dashboard

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Need an interactive dashboard similar to Power BI.

**Decision:** Use Streamlit for the local web-based dashboard.

**Rationale:**
- Runs locally in the browser — no server deployment needed
- Minimal code for interactive widgets, charts, and tables
- Built-in caching for performance
- Easy to extend with new visualizations
- Supports Altair charts for rich interactivity

**Alternative considered:** Dash (Plotly) — more flexible but requires more boilerplate code.

---

## Decision 5: Incremental Data Updates

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Re-fetching all letters on every run would be slow and wasteful.

**Decision:** Compare URLs from the FDA against already-downloaded URLs, only fetch new ones.

**Rationale:**
- First run fetches everything (~30-60 minutes for full texts)
- Subsequent runs only fetch new letters (seconds to minutes)
- Same logic for summarization — only summarize unsummarized letters
- `--full` and `--rescan` flags allow force-refresh when needed

---

## Decision 6: Rate Limiting and Error Handling

**Date:** 2026-03-23
**Status:** Accepted

**Context:** Need to respect FDA servers and handle intermittent failures.

**Decision:** 1.5-second delay between requests, exponential backoff on errors, skip and continue on 404s.

**Rationale:**
- FDA website is a public resource — be respectful
- 1.5s delay keeps fetching under ~40 requests/minute
- Retry with backoff handles temporary 429/5xx errors
- 404s are logged but don't halt the entire fetch process
