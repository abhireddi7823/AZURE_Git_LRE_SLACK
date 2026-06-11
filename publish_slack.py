#!/usr/bin/env python3
"""
publish_slack.py
────────────────
Reads analysis_output/summary.json produced by analyse_reports.py
and posts a rich Slack message (Block Kit) to the configured channel.

Sections posted:
  • Header banner
  • Executive Summary
  • Response Time Table  (as a code block)
  • Slow Transactions
  • Errors
  • Conclusion & Recommendations
  • Links to GitHub Actions run + raw reports
"""

import json
import os
import re
import sys
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── Config ────────────────────────────────────────────────────────────────────
SLACK_TOKEN    = os.environ["SLACK_BOT_TOKEN"]
CHANNEL_ID     = os.environ["SLACK_CHANNEL_ID"]
REPO           = os.environ.get("GITHUB_REPOSITORY",  "unknown/repo")
RUN_ID         = os.environ.get("GITHUB_RUN_ID",      "0")
SERVER_URL     = os.environ.get("GITHUB_SERVER_URL",  "https://github.com")

SUMMARY_PATH   = Path("analysis_output/summary.json")

client = WebClient(token=SLACK_TOKEN)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_section(markdown: str, heading: str) -> str:
    """
    Pull text between ## <heading> and the next ## heading (or end of string).
    Returns empty string if not found.
    """
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, markdown, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _truncate(text: str, limit: int = 2900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…*(truncated)*"


def build_blocks(summary: dict) -> list:
    md       = summary.get("markdown", "")
    model    = summary.get("model_used", "unknown")
    run_url  = summary.get("run_url",   "#")
    repo     = summary.get("repo",      REPO)
    html_rpt = summary.get("html_report",  "")
    trnd_rpt = summary.get("trend_report", "")

    exec_summary   = _extract_section(md, "Executive Summary")
    rt_table       = _extract_section(md, "Response Time Table")
    slow_tx        = _extract_section(md, "Slow Transactions")
    errors         = _extract_section(md, "Errors")
    conclusion     = _extract_section(md, "Conclusion & Recommendations")

    blocks = []

    # ── Header ────────────────────────────────────────────────────────────
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "📊 Load & Performance Test Report", "emoji": True},
    })
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"*Repo:* `{repo}`  |  *Model:* `{model}`  |  *Run:* <{run_url}|#{RUN_ID}>"},
        ],
    })
    blocks.append({"type": "divider"})

    # ── Executive Summary ─────────────────────────────────────────────────
    if exec_summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📝 Executive Summary*\n{_truncate(exec_summary, 2800)}"},
        })
        blocks.append({"type": "divider"})

    # ── Response Time Table ───────────────────────────────────────────────
    if rt_table:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⏱ Response Time Table*"},
        })
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{_truncate(rt_table, 2800)}```"},
        })
        blocks.append({"type": "divider"})

    # ── Slow Transactions ─────────────────────────────────────────────────
    if slow_tx:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🐢 Slow Transactions*\n{_truncate(slow_tx, 2800)}"},
        })
        blocks.append({"type": "divider"})

    # ── Errors ────────────────────────────────────────────────────────────
    error_icon = "🔴" if "no errors" not in errors.lower() else "✅"
    if errors:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{error_icon} Errors*\n{_truncate(errors, 2800)}"},
        })
        blocks.append({"type": "divider"})

    # ── Conclusion & Recommendations ──────────────────────────────────────
    if conclusion:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*💡 Conclusion & Recommendations*\n{_truncate(conclusion, 2800)}"},
        })
        blocks.append({"type": "divider"})

    # ── Footer links ──────────────────────────────────────────────────────
    footer_lines = [f"<{run_url}|🔗 View GitHub Actions Run>"]
    if html_rpt:
        artifact_url = f"{run_url}#artifacts"
        footer_lines.append(f"<{artifact_url}|📄 HTML Report>")
    if trnd_rpt:
        footer_lines.append(f"<{run_url}#artifacts|📈 Trend Report>")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "  |  ".join(footer_lines)},
    })

    return blocks


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not SUMMARY_PATH.exists():
        print(f"ERROR: {SUMMARY_PATH} not found. Did analyse_reports.py run successfully?")
        sys.exit(1)

    summary = json.loads(SUMMARY_PATH.read_text())
    blocks  = build_blocks(summary)

    fallback_text = (
        f"Load & Performance Test Report | Repo: {REPO} | "
        f"Model: {summary.get('model_used','?')} | Run #{RUN_ID}"
    )

    print(f"Posting to Slack channel {CHANNEL_ID} …")
    try:
        resp = client.chat_postMessage(
            channel=CHANNEL_ID,
            text=fallback_text,
            blocks=blocks,
            unfurl_links=False,
        )
        print(f"✅  Posted – timestamp: {resp['ts']}")
    except SlackApiError as exc:
        print(f"ERROR posting to Slack: {exc.response['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
