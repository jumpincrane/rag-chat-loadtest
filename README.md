# StreamlitLoadLab

Realistic load-testing tool for Streamlit-based chatbot applications. Uses Playwright to simulate real user sessions (browsing, typing questions, reading responses) and reports live KPIs (latency, p95, throughput) with JSON exports.

## What it does
- Simulates real user behavior: open app, browse UI, ask a question, wait for the answer, read the response, ask again.
- Runs concurrent "users" with staggered start times (no instant spike).
- Logs live statistics every 60 seconds: active users, requests, avg/p95 latency, errors, QPM.
- Saves raw events and aggregated stats to a timestamped JSON file on exit.
- All test parameters (URL, questions, timings, selectors) are externalized in `config.json`.

## Requirements
- Python 3.13+ (3.10+ should also work)
- Playwright (Chromium)

## Install
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Edit `config.json` to customize the test:

| Key                        | Description                                         | Default                           |
|----------------------------|-----------------------------------------------------|-----------------------------------|
| `app_url`                  | Target application URL                              | `http://localhost:8000/`          |
| `num_users`                | Number of concurrent simulated users                | `1`                               |
| `test_duration`            | Test duration in seconds (0 = unlimited)            | `600`                             |
| `chat_input_placeholder`   | Placeholder text of the chat input element          | `Enter your question...`          |
| `page_ready_selector`      | Playwright selector to confirm page is loaded       | `text=Helpdesk Assistant`         |
| `loading_indicator_text`   | Text shown while the LLM is processing              | `Searching for information`       |
| `questions`                | List of questions to randomly pick from              | *(see config.json)*               |
| `behavior`                 | User behavior timings (exploration, reading, etc.)  | *(see config.json)*               |

## Usage

```bash
# Run with defaults from config.json
python stress_test_standalone.py

# Override URL and user count
python stress_test_standalone.py --url http://myapp.azurewebsites.net -n 5

# Custom config, 5 minutes, verbose logging
python stress_test_standalone.py -c my_config.json -d 300 -v
```

### CLI Arguments

| Flag                   | Description                                         |
|------------------------|-----------------------------------------------------|
| `-c`, `--config`       | Path to JSON config file (default: `config.json`)   |
| `-u`, `--url`          | Target URL (overrides config)                       |
| `-n`, `--users`        | Number of concurrent users (overrides config)       |
| `-d`, `--duration`     | Test duration in seconds (overrides config)         |
| `-v`, `--verbose`      | Enable DEBUG-level logging                          |

## Output

Results are saved to `realistic_stress_test_<timestamp>.json` containing:
- Full test configuration
- Aggregated summary (avg/min/max/p95 response times, success rate)
- Per-question detailed metrics

## Project Structure

```
stress_test_standalone.py   # Main test script
config.json                 # Test configuration
requirements.txt            # Python dependencies
```
