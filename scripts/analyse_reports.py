#!/usr/bin/env python3
"""
analyse_reports.py
──────────────────
• Parses JMeter / LoadRunner / k6 / Gatling HTML performance reports
• Calls Azure AI Foundry (primary → secondary fallback) to generate:
    - Executive Summary
    - Response Time Table  (p50 / p90 / p95 / p99 / max per transaction)
    - Slow Transactions List
    - Errors section
    - Conclusion & Recommendations
• Writes analysis_output/summary.md and sets GITHUB_OUTPUT summary_json
"""

import json
import os
import re
import sys
import textwrap
from pathlib import Path

from bs4 import BeautifulSoup
from openai import AzureOpenAI

# ── Config ────────────────────────────────────────────────────────────────────
ENDPOINT       = os.environ["AZURE_FOUNDRY_ENDPOINT"].rstrip("/")
API_KEY        = os.environ["AZURE_FOUNDRY_API_KEY"]
PRIMARY        = os.environ.get("PRIMARY_DEPLOYMENT",   "gpt-4o")
SECONDARY      = os.environ.get("SECONDARY_DEPLOYMENT", "gpt-4o-mini")
HTML_PATH      = os.environ.get("HTML_REPORT_PATH",  "")
TREND_PATH     = os.environ.get("TREND_REPORT_PATH", "")
REPO           = os.environ.get("GITHUB_REPOSITORY",  "unknown/repo")
RUN_ID         = os.environ.get("GITHUB_RUN_ID",      "0")
SERVER_URL     = os.environ.get("GITHUB_SERVER_URL",  "https://github.com")
OUTPUT_DIR     = Path("analysis_output")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = AzureOpenAI(
    azure_endpoint=ENDPOINT,
    api_key=API_KEY,
    api_version="2024-05-01-preview",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_html(path: str) -> str:
    """Return the visible text of an HTML file (truncated to ~12 000 chars)."""
    if not path or not Path(path).exists():
        return ""
    raw = Path(path).read_text(errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    # Remove script / style noise
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:12_000]


def call_foundry(deployment: str, system: str, user: str) -> str:
    """Call Azure AI Foundry and return the assistant reply text."""
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    return response.choices[0].message.content.strip()


def analyse(html_text: str, trend_text: str) -> dict:
    """Run analysis; fall back to secondary model on error."""
    system_prompt = textwrap.dedent("""
        You are a senior performance-engineering consultant.
        Analyse the provided load / performance test data and produce a
        structured report with EXACTLY these sections, using the headings shown:

        ## Executive Summary
        2-4 paragraphs: overall health, key metrics, whether SLAs were met.

        ## Response Time Table
        A markdown table with columns:
        | Transaction | Samples | Mean (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Max (ms) | Error % |

        ## Slow Transactions
        Bullet list of transactions where p90 > 2 000 ms or error rate > 1 %.
        For each, give the p90 value and a short root-cause hypothesis.

        ## Errors
        If errors exist, list each unique error message, count, and likely cause.
        If none, write "No errors detected."

        ## Conclusion & Recommendations
        Numbered list of actionable recommendations ordered by priority.

        Keep language professional and concise.  Use markdown formatting.
    """).strip()

    user_prompt = (
        f"### HTML Performance Report\n\n{html_text or '(not provided)'}\n\n"
        f"### Trend Report\n\n{trend_text or '(not provided)'}\n"
    )

    for model in (PRIMARY, SECONDARY):
        try:
            print(f"  → Calling Azure AI Foundry model: {model}")
            return {
                "model_used": model,
                "content": call_foundry(model, system_prompt, user_prompt),
            }
        except Exception as exc:
            print(f"  ⚠  Model {model} failed: {exc}")

    raise RuntimeError("Both primary and secondary Azure AI Foundry models failed.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"HTML report  : {HTML_PATH or '(none)'}")
    print(f"Trend report : {TREND_PATH or '(none)'}")

    html_text  = read_html(HTML_PATH)
    trend_text = read_html(TREND_PATH)

    if not html_text and not trend_text:
        print("⚠  No report content found – writing placeholder analysis.")
        html_text = "No report content available. Please ensure reports/ folder contains HTML files."

    result = analyse(html_text, trend_text)
    model_used = result["model_used"]
    markdown   = result["content"]

    # ── Persist markdown ──────────────────────────────────────────────────
    md_path = OUTPUT_DIR / "summary.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"✅  Analysis written → {md_path}")

    # ── Persist JSON (used by publish_slack.py) ───────────────────────────
    run_url = f"{SERVER_URL}/{REPO}/actions/runs/{RUN_ID}"
    summary_obj = {
        "model_used":  model_used,
        "run_url":     run_url,
        "repo":        REPO,
        "html_report": HTML_PATH,
        "trend_report": TREND_PATH,
        "markdown":    markdown,
    }
    json_path = OUTPUT_DIR / "summary.json"
    json_path.write_text(json.dumps(summary_obj, ensure_ascii=False, indent=2))

    # ── Write to GITHUB_OUTPUT ────────────────────────────────────────────
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        # Multi-line output must use heredoc syntax
        with open(gh_output, "a") as fh:
            escaped = json.dumps(json.dumps(summary_obj))   # double-encode for safety
            fh.write(f"summary_json={escaped}\n")

    print(f"Model used : {model_used}")
    print("Done.")


if __name__ == "__main__":
    main()
