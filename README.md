# StreamlitLoadLab

Realistic load-testing harness tailored to our Streamlit RAG chatbot stack (Azure App Service + Azure OpenAI + Azure AI Search). Playwright scenarios mimic real user sessions and capture live KPIs (latency, p95, throughput) with JSON/CSV exports.

## What it does
- Simulates real user behavior: open app, browse UI, ask a question, wait for the answer, read for 30–35s, ask again.
- Runs many concurrent “users” with staggered start (no instant spike unless you want it).
- Prints a live summary (e.g., every minute): active users, requests, avg/p95 latency, errors, QPM.
- Saves raw events and aggregated stats to `results/*.json` and/or `results/*.csv`.

## Requirements
- Python 3.10+
- Playwright (Chromium)

## Install
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
