# How to Add "Bring Your Own API Key" to the Dashboard

This guide explains how to let each user enter their own OpenAI API key in the dashboard, so your hosted deployment doesn't consume your tokens.

## Overview

You'll make 3 small changes:

1. **`dashboard.py`** — Add a sidebar input for the API key + pass it to the Q&A function
2. **`utils/summarizer.py`** — Already supports a custom `api_key` parameter (no change needed)
3. **Remove your key from Railway** — So your key isn't used by default

---

## Step 1: Edit `dashboard.py`

### 1a. Add a sidebar input for the API key

Find this block near the top of the file (around line 24–30, after `st.set_page_config`):

```python
st.set_page_config(
    page_title="FDA Warning Letter Analysis",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

**Right after it**, add:

```python
# ── User API Key Input ────────────────────────────────────────────────────
with st.sidebar:
    user_api_key = st.text_input(
        "🔑 OpenAI API Key (optional)",
        type="password",
        help="Enter your own OpenAI API key to enable AI-powered Q&A and summaries. "
             "Without a key, the system uses rule-based analysis (still works well).",
        placeholder="sk-..."
    )
    if user_api_key:
        st.success("API key set for this session")
    else:
        st.info("No API key → using rule-based analysis")
```

### 1b. Use the user's key instead of the server key in Q&A

Find the `answer_question` function (around line 910). It currently looks like:

```python
if OPENAI_API_KEY:
```

**Change it to:**

```python
active_key = user_api_key or OPENAI_API_KEY
if active_key:
```

Then find the `_answer_with_openai` function call and the function itself.

In the **call** (around line 919), change:

```python
return _answer_with_openai(question, filtered_df)
```

**To:**

```python
return _answer_with_openai(question, filtered_df, api_key=active_key)
```

In the **function definition** (around line 987), change:

```python
def _answer_with_openai(question, df):
```

**To:**

```python
def _answer_with_openai(question, df, api_key=None):
```

And where it creates the client (around line 1025), change:

```python
client = OpenAI(api_key=OPENAI_API_KEY)
```

**To:**

```python
client = OpenAI(api_key=api_key or OPENAI_API_KEY)
```

---

## Step 2: Remove your API key from Railway

1. Go to your Railway project dashboard
2. Click on your service → **Variables** tab
3. **Delete** the `OPENAI_API_KEY` variable (or set it to empty)
4. Redeploy

Now only users who enter their own key will get AI features. Everyone else gets the rule-based analysis, which still works well.

---

## Step 3 (Optional): Add a note in the Insights tab

If you want to make it extra clear to users, find the Insights & Q&A tab section in `dashboard.py` and add a note:

```python
st.caption("💡 Enter your OpenAI API key in the sidebar to enable AI-powered Q&A")
```

---

## That's it!

After these changes:
- **Without a key**: Users see all data, charts, and rule-based summaries — fully functional
- **With a key**: Users also get AI-powered Q&A and can re-summarize letters with GPT
- **Your tokens**: Not used at all (since you removed your key from Railway)

Each user's key is only stored in their browser session and is never saved to disk.
