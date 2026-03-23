"""
Dual-mode summarization engine for FDA warning letters.

Mode 1: OpenAI GPT — sends letter text to GPT for structured extraction.
Mode 2: Rule-based — uses regex patterns to extract observations, violations, etc.
"""

import re
import json
import logging

from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_TOKENS, MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


# ── OpenAI GPT Summarization ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are an FDA regulatory analyst. Extract structured information from this FDA warning letter.

Return a JSON object with exactly these keys:
- "summary": 2-3 sentence overview of the letter
- "key_observations": list of strings, each a distinct observation/finding
- "violations": list of specific CFR citations found (e.g., "21 CFR 211.67")
- "product_types": list of product categories mentioned (e.g., "Drugs", "Devices", "Food")
- "corrective_actions": list of corrective actions FDA requires

Return ONLY valid JSON, no other text."""


def summarize_with_openai(text, api_key=None):
    """
    Summarize a warning letter using OpenAI API.

    Returns dict with summary fields, or None on failure.
    """
    key = api_key or OPENAI_API_KEY
    if not key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)

        # Truncate very long letters
        truncated = text[:MAX_TEXT_LENGTH]

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=OPENAI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract information from this FDA warning letter:\n\n{truncated}"},
            ],
        )

        response_text = response.choices[0].message.content

        # Parse JSON from response
        # Handle cases where GPT wraps JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
        if json_match:
            response_text = json_match.group(1)

        result = json.loads(response_text)

        # Validate expected keys
        expected_keys = {"summary", "key_observations", "violations", "product_types", "corrective_actions"}
        for k in expected_keys:
            if k not in result:
                result[k] = [] if k != "summary" else "Summary not available."

        result["method"] = "openai"
        return result

    except ImportError:
        logger.warning("openai package not installed. Install with: pip install openai")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None


# ── Rule-Based Summarization ──────────────────────────────────────────────

# Common FDA observation patterns
OBSERVATION_PATTERNS = [
    r'(?:observation\s*\d*[:.]\s*)(.*?)(?=\n\n|observation\s*\d|$)',
    r'(?:we observed|we noted|our inspection revealed|it was observed that)\s+(.*?)(?:\.|$)',
    r'(?:failure to|failed to)\s+(.*?)(?:\.|$)',
    r'(?:your firm did not|your firm failed to|your firm does not)\s+(.*?)(?:\.|$)',
    r'(?:there (?:is|was|were) no)\s+(.*?)(?:\.|$)',
    r'(?:inadequate|insufficient)\s+(.*?)(?:\.|$)',
]

# CFR citation pattern
CFR_PATTERN = r'21\s*C\.?F\.?R\.?\s*(?:Part\s*)?(\d+(?:\.\d+)?(?:\([a-z]\)(?:\(\d+\))?)?)'

# Product type keywords
PRODUCT_KEYWORDS = {
    "drug": "Drugs",
    "pharmaceutical": "Drugs",
    "cgmp": "Drugs/CGMP",
    "api": "Active Pharmaceutical Ingredient",
    "device": "Devices",
    "medical device": "Devices",
    "biologic": "Biologics",
    "blood": "Biologics",
    "food": "Food",
    "dietary supplement": "Dietary Supplements",
    "cosmetic": "Cosmetics",
    "tobacco": "Tobacco",
    "veterinary": "Veterinary",
    "animal": "Veterinary",
}

# Corrective action patterns
CORRECTIVE_PATTERNS = [
    r'(?:you should|we recommend|fda recommends)\s+(.*?)(?:\.|$)',
    r'(?:within\s+(?:fifteen|30|60|90)\s+(?:business\s+)?(?:days?|working days?))\s*(.*?)(?:\.|$)',
    r'(?:please (?:provide|submit|respond|correct|address))\s+(.*?)(?:\.|$)',
    r'(?:corrective action[s]?\s*(?:include|should|must)?)\s*(.*?)(?:\.|$)',
]


def summarize_rule_based(text):
    """
    Extract structured information using regex patterns.

    Returns dict with same schema as OpenAI version.
    """
    if not text or len(text.strip()) < 50:
        return {
            "summary": "Letter text not available or too short to analyze.",
            "key_observations": [],
            "violations": [],
            "product_types": [],
            "corrective_actions": [],
            "method": "rule_based",
        }

    text_lower = text.lower()

    # Extract observations
    observations = []
    for pattern in OBSERVATION_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            clean = match.strip()
            if len(clean) > 20 and clean not in observations:
                obs = clean[0].upper() + clean[1:]
                if len(obs) > 300:
                    obs = obs[:297] + "..."
                observations.append(obs)

    # Also look for numbered items (1., 2., etc.) which are common in letters
    numbered = re.findall(r'\n\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.|$)', text, re.DOTALL)
    for num, content in numbered:
        clean = content.strip().replace("\n", " ")[:300]
        if len(clean) > 20 and clean not in observations:
            observations.append(clean)

    # Deduplicate similar observations
    observations = _deduplicate(observations)[:20]

    # Extract CFR violations
    cfr_matches = re.findall(CFR_PATTERN, text)
    violations = list(dict.fromkeys(f"21 CFR {m}" for m in cfr_matches))

    # Detect product types
    product_types = []
    for keyword, ptype in PRODUCT_KEYWORDS.items():
        if keyword in text_lower and ptype not in product_types:
            product_types.append(ptype)

    # Extract corrective actions
    corrective_actions = []
    for pattern in CORRECTIVE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            clean = match.strip()
            if len(clean) > 15:
                action = clean[0].upper() + clean[1:]
                if len(action) > 300:
                    action = action[:297] + "..."
                corrective_actions.append(action)
    corrective_actions = _deduplicate(corrective_actions)[:10]

    # Generate summary
    summary_parts = []
    if product_types:
        summary_parts.append(f"This warning letter relates to {', '.join(product_types[:3])}.")
    if observations:
        summary_parts.append(f"The FDA identified {len(observations)} observation(s).")
    if violations:
        summary_parts.append(f"Cited violations include {', '.join(violations[:3])}.")
    if not summary_parts:
        summary_parts.append("Warning letter content analyzed.")

    summary = " ".join(summary_parts)

    return {
        "summary": summary,
        "key_observations": observations,
        "violations": violations,
        "product_types": product_types,
        "corrective_actions": corrective_actions,
        "method": "rule_based",
    }


def _deduplicate(items, threshold=0.7):
    """Remove near-duplicate strings based on word overlap."""
    if not items:
        return []

    unique = [items[0]]
    for item in items[1:]:
        words_new = set(item.lower().split())
        is_dup = False
        for existing in unique:
            words_existing = set(existing.lower().split())
            if not words_new or not words_existing:
                continue
            overlap = len(words_new & words_existing) / min(len(words_new), len(words_existing))
            if overlap > threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(item)
    return unique


# ── Public Interface ──────────────────────────────────────────────────────

def summarize_letter(text, api_key=None, method=None):
    """
    Summarize a single warning letter.

    Args:
        text: full text of the letter
        api_key: optional OpenAI API key
        method: force "openai" or "rules". If None, tries OpenAI first.

    Returns:
        dict with summary, key_observations, violations, product_types,
        corrective_actions, method
    """
    if method == "rules":
        return summarize_rule_based(text)

    if method == "openai" or (method is None and (api_key or OPENAI_API_KEY)):
        result = summarize_with_openai(text, api_key)
        if result:
            return result
        logger.info("OpenAI summarization failed, falling back to rule-based")

    return summarize_rule_based(text)
