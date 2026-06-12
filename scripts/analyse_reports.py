#!/usr/bin/env python3
"""
analyse_reports.py
──────────────────
• Parses HTML performance reports (JMeter, Gatling, k6, LoadRunner)
• Calls Azure AI Foundry (primary → secondary fallback) using the
  VERIFIED endpoint format (same as azure-foundry-connection-test.yml):
    https://lre-performance-project-resource.services.ai.azure.com/openai/v1/chat/completions
  Header: api-key: <key>   (NO api-version query param needed)
• Produces structured analysis:
    - Executive Summary
    - Response Time Table
    - Slow Transactions
    - Errors
    - Conclusion & Recommendations
• Writes analysis_output/summary.md and analysis_output/summary.json
"""

import json
import os
import re
import textwrap
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY  = os.environ["AZURE_FOUNDRY_API_KEY"]

# IMPORTANT: Same endpoint format verified working in
# azure-foundry-connection-test.yml — NO api-version query param.
ENDPOINT = os.environ.get(
    "AZURE_FOUNDRY_ENDPOINT",
    "https://lre-performance-project-resource.services.ai.azure.com/openai/v1"
).rstrip("/")

PRIMARY    = os.environ.get("PRIMARY_DEPLOYMENT",   "gpt-4o")
SECONDARY  = os.environ.get("SECONDARY_DEPLOYMENT", "gpt-4o-mini")

HTML_PATH  = os.environ.get("HTML_REPORT_PATH",  "")
TREND_PATH = os.environ.get("TREND_REPORT_PATH", "")

REPO       = os.environ.get("GITHUB_REPOSITORY",  "unknown/repo")
RUN_ID     = os.environ.get("GITHUB_RUN_ID",      "0")
SERVER_URL = os.environ.get("GITHUB_SERVER_URL",  "https://github.com")

OUTPUT_DIR = Path("analysis_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Verified working URL — no api-version param
CHAT_URL = f"{ENDPOINT}/chat/completions"


# ── Helpers ─────────────────────────────────────────────────────────────────

def read_html(path: str) -> str:
    """Return visible text of an HTML file (truncated)."""
    if not path or not Path(path).exists():
        return ""
    raw = Path(path).read_text(errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:12_000]


def call_foundry(model: str, system: str, user: str) -> str:
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
    }
    r = requests.post(CHAT_URL, headers=headers, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"].strip()


SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior performance-engineering consultant.
    Analyse the provided load / performance test data and produce a
    structured report with EXACTLY these sections, using the headings shown:

    ## Executive Summary
    2-4 paragraphs: overall health, key metrics, whether SLAs were met.

    ## Response Time Table
    A markdown table with columns:
    | Transaction | Samples | Mean (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Max (ms) | Error % |

    ## Slow Transactions
    Bullet list of transactions where p90 > 2000 ms or error rate > 1%.
    For each, give the p90 value and a short root-cause hypothesis.

    ## Errors
    If errors exist, list each unique error message, count, and likely cause.
    If none, write "No errors detected."

    ## Conclusion & Recommendations
    Numbered list of actionable recommendations ordered by priority.

    Keep language professional and concise. Use markdown formatting.
""").strip()


def analyse(html_text: str, trend_text: str) -> dict:
    user_prompt = (
        f"### HTML Performance Report\n\n{html_text or '(not provided)'}\n\n"
        f"### Trend Report\n\n{trend_text or '(not provided)'}\n"
    )

    for model in (PRIMARY, SECONDARY):
        try:
            print(f"  → Calling Azure AI Foundry model: {model}")
            content = call_foundry(model, SYSTEM_PROMPT, user_prompt)
            return {"model_used": model, "content": content}
        except Exception as exc:
            print(f"  ⚠  Model {model} failed: {exc}")

    raise RuntimeError("Both primary and secondary Azure AI Foundry models failed.")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"Endpoint     : {ENDPOINT}")
    print(f"Chat URL     : {CHAT_URL}")
    print(f"Primary      : {PRIMARY}")
    print(f"Secondary    : {SECONDARY}")
    print(f"HTML report  : {HTML_PATH or '(none)'}")
    print(f"Trend report : {TREND_PATH or '(none)'}")

    html_text  = read_html(HTML_PATH)
    trend_text = read_html(TREND_PATH)

    if not html_text and not trend_text:
        print("⚠  No report content found – using placeholder text.")
        html_text = (
            "No report content available. "
            "Please ensure the reports/ folder contains valid HTML files."
        )

    result     = analyse(html_text, trend_text)
    model_used = result["model_used"]
    markdown   = result["content"]

    # Persist markdown
    md_path = OUTPUT_DIR / "summary.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"\n✅  Analysis written → {md_path}")

    # Persist JSON for Slack publisher (used later)
    run_url = f"{SERVER_URL}/{REPO}/actions/runs/{RUN_ID}"
    summary_obj = {
        "model_used":   model_used,
        "run_url":      run_url,
        "repo":         REPO,
        "html_report":  HTML_PATH,
        "trend_report": TREND_PATH,
        "markdown":     markdown,
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary_obj, ensure_ascii=False, indent=2)
    )

    print(f"Model used : {model_used}")
    print("Done.")


if __name__ == "__main__":
    main()
