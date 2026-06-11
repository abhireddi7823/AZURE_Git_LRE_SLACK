# AZURE_Git_LRE_SLACK – Performance Report Pipeline

> **Azure AI Foundry ↔ GitHub Actions ↔ Slack**  
> Automatically analyses load-test HTML reports with AI and publishes rich results to Slack.

---

## Repository Layout

```
AZURE_Git_LRE_SLACK/
├── .github/
│   └── workflows/
│       └── performance-report-pipeline.yml   ← the YAML workflow
├── scripts/
│   ├── analyse_reports.py                    ← Azure AI Foundry analysis
│   └── publish_slack.py                      ← Slack publisher
├── reports/                                  ← Drop HTML reports here
│   ├── latest/
│   │   └── index.html                        ← JMeter / Gatling / k6 report
│   └── trend/
│       └── trend.html                        ← Trend report (optional)
└── analysis_output/                          ← Auto-generated (gitignored)
    ├── summary.md
    └── summary.json
```

---

## 1 · Azure AI Foundry – Models Used

| Role | Model | Purpose |
|------|-------|---------|
| **Primary** | `gpt-4o` | Deep analysis, structured report generation |
| **Fallback** | `gpt-4o-mini` | Cost-efficient fallback if primary is unavailable |

Both are Azure OpenAI deployments inside your Azure AI Foundry hub.  
You can override them via GitHub Secrets (see below).

---

## 2 · GitHub Secrets Required

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Value |
|-------------|-------|
| `AZURE_FOUNDRY_API_KEY` | Your Azure AI Foundry / Azure OpenAI API key |
| `AZURE_FOUNDRY_ENDPOINT` | `https://<your-hub>.openai.azure.com/` |
| `AZURE_FOUNDRY_DEPLOYMENT_PRIMARY` | e.g. `gpt-4o` |
| `AZURE_FOUNDRY_DEPLOYMENT_SECONDARY` | e.g. `gpt-4o-mini` |
| `SLACK_BOT_TOKEN` | `xoxb-...` (Bot User OAuth Token) |
| `SLACK_CHANNEL_ID` | e.g. `C0XXXXXXXXX` (channel ID, not name) |

### How to get SLACK_CHANNEL_ID
1. Open Slack → right-click the channel → **Copy link**  
2. The ID is the last part: `https://app.slack.com/client/TXXX/**C0XXXXXXXXX**`

### How to get AZURE_FOUNDRY_ENDPOINT
Azure Portal → Azure AI Foundry → your hub → **Keys and Endpoint** → copy the endpoint URL.

---

## 3 · Azure AI Foundry Connection (in YAML)

The workflow connects via the official Azure OpenAI REST API (`/v1/messages`) using:

```yaml
env:
  AZURE_FOUNDRY_API_KEY:   ${{ secrets.AZURE_FOUNDRY_API_KEY }}
  AZURE_FOUNDRY_ENDPOINT:  ${{ secrets.AZURE_FOUNDRY_ENDPOINT }}
```

The Python `openai` SDK is configured as:

```python
from openai import AzureOpenAI
client = AzureOpenAI(
    azure_endpoint = os.environ["AZURE_FOUNDRY_ENDPOINT"],
    api_key        = os.environ["AZURE_FOUNDRY_API_KEY"],
    api_version    = "2024-05-01-preview",
)
```

---

## 4 · How to Use

### Auto-trigger (push reports)
Simply push / commit HTML report files under `reports/`:
```bash
cp /your/jmeter/output/index.html  reports/latest/index.html
cp /your/jmeter/trend/trend.html   reports/trend/trend.html
git add reports/
git commit -m "chore: add performance test results run-42"
git push
```
The workflow triggers automatically on push to `main` or `develop`.

### Manual trigger
1. GitHub → **Actions** → **LRE Performance Report – Azure Foundry + Slack**  
2. Click **Run workflow** → enter optional paths → **Run**

---

## 5 · Report Output Sections

Each Slack message contains:

| Section | Description |
|---------|-------------|
| 📝 **Executive Summary** | Overall health, SLA verdict, key metrics |
| ⏱ **Response Time Table** | p50/p90/p95/p99/Max per transaction |
| 🐢 **Slow Transactions** | p90 > 2 000 ms or error rate > 1 % |
| 🔴 **Errors** | Unique errors with counts and root-cause hypotheses |
| 💡 **Conclusion & Recommendations** | Prioritised action items |

---

## 6 · Supported Report Formats

The parser extracts visible text from any HTML report, so it works with:
- **Apache JMeter** (HTML dashboard)  
- **Gatling** (simulation report)  
- **k6** (HTML reporter)  
- **LoadRunner / NeoLoad** (HTML exports)  
- Any tool that produces an `index.html` summary

---

## 7 · Slack App Setup (one-time)

1. Go to https://api.slack.com/apps → **Create New App** → From scratch  
2. Name it `LRE Reporter`, pick your workspace  
3. **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `chat:write.public`  
4. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`)  
5. Invite the bot to your channel: `/invite @LRE Reporter`
