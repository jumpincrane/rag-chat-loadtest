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
| `chat_input_placeholder`   | Placeholder text of the chat input field (see below)| `Enter your question...`          |
| `page_ready_title`         | Browser tab title confirming the page loaded (see below) | `Helpdesk Assistant`         |
| `loading_indicator_text`   | Text shown while the LLM is processing              | `Searching for information`       |
| `questions`                | List of questions to randomly pick from              | *(see config.json)*               |
| `behavior`                 | User behavior timings (see below)                   | *(see config.json)*               |

### How to find `chat_input_placeholder`

This is the greyed-out hint text inside the chat input field. Open your app in a browser, look at the text box where users type messages — the light text shown before typing is the placeholder. You can also inspect the element (F12 > click the input) and look for the `placeholder="..."` attribute.

### How to find `page_ready_title`

This is the text shown in the browser tab (the page title). Open your app and look at the tab — whatever text appears there is what you put here. The script waits for `document.title` to contain this string before interacting with the page.

### Behavior timings

The `behavior` object controls how simulated users pace their actions. All values are `[min, max]` ranges in seconds — the script picks a random value within the range each time.

| Key                        | What it controls                                                        | Default       |
|----------------------------|-------------------------------------------------------------------------|---------------|
| `initial_page_exploration` | How long the user looks around after the page loads                     | `[3, 8]`      |
| `before_first_question`    | Pause before typing the first question                                  | `[2, 5]`      |
| `reading_response`         | How long the user reads the chatbot's answer before doing anything else | `[25, 40]`    |
| `between_questions`        | Pause between follow-up questions in the same session                   | `[5, 15]`     |
| `menu_browsing`            | Time spent browsing sidebar/menu (happens randomly, ~30% of sessions)   | `[3, 7]`      |
| `questions_per_session`    | How many questions a user asks per session                              | `[2, 5]`      |

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
