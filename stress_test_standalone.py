# stress_test_standalone.py
import argparse
import json
import logging
import random
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger("stress_test")

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(config_path: str) -> dict:
    """Load test configuration from a JSON file."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Convert behavior lists to tuples for random.uniform/randint
    behavior = cfg.get("behavior", {})
    for key, val in behavior.items():
        if isinstance(val, list) and len(val) == 2:
            behavior[key] = tuple(val)
    cfg["behavior"] = behavior
    return cfg


class MetricsCollector:
    def __init__(self, config: dict):
        self.config = config
        self.lock = threading.RLock()
        self.metrics = []
        self.active_users = 0
        self.completed_sessions = 0
        self.failed_sessions = 0
        self.total_questions = 0
        self.start_time = time.time()

        # Additional metrics for summary
        self.user_activities = {}  # Track current activity per user

    def add_metric(self, metric):
        with self.lock:
            self.metrics.append(metric)
            if metric.get("success"):
                self.total_questions += 1

    def user_started(self):
        with self.lock:
            self.active_users += 1

    def user_finished(self, success=True):
        with self.lock:
            self.active_users -= 1
            if success:
                self.completed_sessions += 1
            else:
                self.failed_sessions += 1

    def update_user_activity(self, user_id, activity):
        """Update the current activity for a given user."""
        with self.lock:
            self.user_activities[user_id] = {"activity": activity, "timestamp": time.time()}

    def get_user_activities(self):
        """Return a snapshot of all user activities."""
        with self.lock:
            return dict(self.user_activities)

    def get_stats(self):
        with self.lock:
            if not self.metrics:
                return None

            query_times = [m["query_time"] for m in self.metrics if m.get("success") and "query_time" in m]
            load_times = [
                m["load_time"] for m in self.metrics if m.get("success") and "load_time" in m and m["load_time"] > 0
            ]

            return {
                "total_questions": self.total_questions,
                "completed_sessions": self.completed_sessions,
                "failed_sessions": self.failed_sessions,
                "active_users": self.active_users,
                "avg_query_time": statistics.mean(query_times) if query_times else 0,
                "min_query_time": min(query_times) if query_times else 0,
                "max_query_time": max(query_times) if query_times else 0,
                "p95_query_time": statistics.quantiles(query_times, n=20)[18]
                if len(query_times) >= 20
                else (max(query_times) if query_times else 0),
                "avg_load_time": statistics.mean(load_times) if load_times else 0,
                "elapsed_time": time.time() - self.start_time,
            }

    def get_last_minute_stats(self):
        """Return aggregated statistics from the last 60 seconds."""
        with self.lock:
            current_time = time.time()
            one_minute_ago = current_time - 60

            recent_metrics = [
                m
                for m in self.metrics
                if m.get("timestamp") and datetime.fromisoformat(m["timestamp"]).timestamp() > one_minute_ago
            ]

            if not recent_metrics:
                return None

            successful = [m for m in recent_metrics if m.get("success")]
            query_times = [m["query_time"] for m in successful if "query_time" in m]

            return {
                "questions_last_minute": len(successful),
                "avg_response_time": statistics.mean(query_times) if query_times else 0,
                "failed_last_minute": len([m for m in recent_metrics if not m.get("success")]),
            }

    def save_to_file(self, filename="stress_test_results.json"):
        with self.lock:
            data = {
                "test_config": {
                    "app_url": self.config["app_url"],
                    "num_users": self.config["num_users"],
                    "test_duration": self.config["test_duration"],
                    "behavior_settings": {
                        k: list(v) if isinstance(v, tuple) else v for k, v in self.config["behavior"].items()
                    },
                    "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                },
                "summary": self.get_stats(),
                "detailed_metrics": self.metrics,
            }

            with open(filename, "w") as f:
                json.dump(data, f, indent=2)

            logger.info("Results saved to %s", filename)


def realistic_user_session(user_id, stop_event, config, collector):
    """Simulate a realistic user session with activity tracking."""
    app_url = config["app_url"]
    questions = config["questions"]
    behavior = config["behavior"]
    chat_placeholder = config.get("chat_input_placeholder", "Enter your question...")
    page_ready = config.get("page_ready_selector", "")
    loading_text = config.get("loading_indicator_text", "Searching for information")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])

        try:
            collector.user_started()
            session_num = 0

            while not stop_event.is_set():
                session_num += 1
                logger.info("User %d - Session %d started", user_id, session_num)

                page = browser.new_page()

                try:
                    # Phase 1: Load the page
                    collector.update_user_activity(user_id, "Loading page")
                    start_load = time.time()
                    page.goto(app_url, wait_until="networkidle", timeout=30000)
                    load_time = time.time() - start_load
                    logger.info("User %d - Page loaded in %.2fs", user_id, load_time)

                    if page_ready:
                        page.wait_for_selector(page_ready, timeout=10000)

                    # Phase 2: Explore the interface
                    collector.update_user_activity(user_id, "Exploring interface")
                    exploration_time = random.uniform(*behavior["initial_page_exploration"])
                    logger.debug("User %d - Exploring (%.1fs)", user_id, exploration_time)
                    if stop_event.wait(exploration_time):
                        break

                    # Randomly browse the Prompt Guide
                    if random.random() < 0.3:
                        collector.update_user_activity(user_id, "Browsing Prompt Guide")
                        logger.debug("User %d - Browsing Prompt Guide", user_id)
                        browse_time = random.uniform(*behavior["menu_browsing"])
                        if stop_event.wait(browse_time):
                            break

                    # Phase 3: Ask questions
                    num_questions = random.randint(*behavior["questions_per_session"])
                    logger.info("User %d - Will ask %d questions", user_id, num_questions)

                    for q_num in range(1, num_questions + 1):
                        if stop_event.is_set():
                            break

                        # Pause before asking
                        if q_num == 1:
                            collector.update_user_activity(user_id, "Thinking what to ask")
                            thinking_time = random.uniform(*behavior["before_first_question"])
                            logger.debug("User %d - Thinking (%.1fs)", user_id, thinking_time)
                            if stop_event.wait(thinking_time):
                                break
                        else:
                            collector.update_user_activity(user_id, "Pause between questions")
                            between_time = random.uniform(*behavior["between_questions"])
                            logger.debug("User %d - Pause (%.1fs)", user_id, between_time)
                            if stop_event.wait(between_time):
                                break

                        chat_input = page.get_by_placeholder(chat_placeholder)
                        question = random.choice(questions)

                        collector.update_user_activity(user_id, f"Typing question {q_num}/{num_questions}")
                        logger.info("User %d Q%d/%d - Typing: %s...", user_id, q_num, num_questions, question[:40])

                        chat_input.click()
                        time.sleep(random.uniform(0.3, 0.8))
                        chat_input.fill(question)
                        time.sleep(random.uniform(0.2, 0.5))

                        collector.update_user_activity(user_id, f"Waiting for response {q_num}/{num_questions}")
                        start_query = time.time()
                        chat_input.press("Enter")
                        logger.info("User %d Q%d/%d - Sent, waiting...", user_id, q_num, num_questions)

                        try:
                            page.wait_for_selector(f"text={loading_text}", timeout=5000)
                            logger.debug("User %d Q%d/%d - LLM processing...", user_id, q_num, num_questions)
                        except Exception:
                            pass

                        try:
                            page.wait_for_selector(f"text={loading_text}", state="detached", timeout=60000)

                            query_time = time.time() - start_query
                            logger.info("User %d Q%d/%d - Response in %.2fs", user_id, q_num, num_questions, query_time)

                            collector.add_metric(
                                {
                                    "user_id": user_id,
                                    "session_num": session_num,
                                    "question_num": q_num,
                                    "question": question,
                                    "load_time": load_time if q_num == 1 else 0,
                                    "query_time": query_time,
                                    "timestamp": datetime.now().isoformat(),
                                    "success": True,
                                }
                            )

                            # Phase 4: Read the response
                            collector.update_user_activity(user_id, f"Reading response {q_num}/{num_questions}")
                            reading_time = random.uniform(*behavior["reading_response"])
                            logger.debug(
                                "User %d Q%d/%d - Reading (%.1fs)", user_id, q_num, num_questions, reading_time
                            )

                            if stop_event.wait(reading_time):
                                break

                        except Exception as e:
                            query_time = time.time() - start_query
                            logger.error(
                                "User %d Q%d/%d - Error after %.2fs", user_id, q_num, num_questions, query_time
                            )

                            collector.add_metric(
                                {
                                    "user_id": user_id,
                                    "session_num": session_num,
                                    "question_num": q_num,
                                    "question": question,
                                    "error": str(e),
                                    "timestamp": datetime.now().isoformat(),
                                    "success": False,
                                }
                            )
                            break

                    logger.info("User %d - Session %d completed", user_id, session_num)
                    page.close()

                    # Decide whether to start a new session
                    if random.random() < 0.4:
                        collector.update_user_activity(user_id, "Waiting to start new session")
                        reset_wait = random.uniform(10, 30)
                        logger.info("User %d - New session in %.1fs", user_id, reset_wait)
                        if stop_event.wait(reset_wait):
                            break
                    else:
                        logger.info("User %d - Leaving", user_id)
                        break

                except Exception as e:
                    logger.error("User %d Session %d - Error: %s", user_id, session_num, e)
                    collector.add_metric(
                        {
                            "user_id": user_id,
                            "session_num": session_num,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                            "success": False,
                        }
                    )
                    break

            collector.user_finished(success=True)
            collector.update_user_activity(user_id, "Finished")
            logger.info("User %d - Finished (%d sessions)", user_id, session_num)

        except Exception as e:
            logger.critical("User %d - Fatal error: %s", user_id, e)
            collector.user_finished(success=False)

        finally:
            browser.close()


def print_live_stats(collector):
    """Log live statistics every 60 seconds."""
    last_full_report = time.time()

    while True:
        time.sleep(10)  # Check every 10 seconds

        current_time = time.time()

        # Full report every 60 seconds
        if current_time - last_full_report >= 60:
            stats = collector.get_stats()
            last_min_stats = collector.get_last_minute_stats()

            if stats:
                elapsed_min = stats["elapsed_time"] / 60
                lines = [
                    "",
                    "=" * 70,
                    f"LIVE STATISTICS - {datetime.now().strftime('%H:%M:%S')}",
                    "=" * 70,
                    f"  Elapsed:              {int(elapsed_min)} min {int(stats['elapsed_time'] % 60)} sec",
                    f"  Active users:         {stats['active_users']}",
                    f"  Completed sessions:   {stats['completed_sessions']}",
                    f"  Failed sessions:      {stats['failed_sessions']}",
                    f"  Total questions:      {stats['total_questions']}",
                ]

                if stats["total_questions"] > 0:
                    qpm = (stats["total_questions"] / stats["elapsed_time"]) * 60
                    lines.append(f"  Avg questions/min:    {qpm:.2f}")

                lines += [
                    "",
                    "  OVERALL RESPONSE TIMES:",
                    f"   Average:             {stats['avg_query_time']:.2f}s",
                    f"   Min:                 {stats['min_query_time']:.2f}s",
                    f"   Max:                 {stats['max_query_time']:.2f}s",
                    f"   P95:                 {stats['p95_query_time']:.2f}s",
                ]

                if stats["avg_load_time"] > 0:
                    lines += [
                        "",
                        "  PAGE LOAD:",
                        f"   Average:             {stats['avg_load_time']:.2f}s",
                    ]

                if last_min_stats:
                    lines += [
                        "",
                        "  LAST MINUTE:",
                        f"   Questions:           {last_min_stats['questions_last_minute']}",
                        f"   Avg response:        {last_min_stats['avg_response_time']:.2f}s",
                        f"   Failed:              {last_min_stats['failed_last_minute']}",
                    ]

                activities = collector.get_user_activities()
                if activities:
                    lines.append("")
                    lines.append("  USER ACTIVITIES:")
                    for uid, activity_info in sorted(activities.items()):
                        activity = activity_info["activity"]
                        age = int(current_time - activity_info["timestamp"])
                        lines.append(f"   User {uid:2d}: {activity:40s} ({age}s ago)")

                lines.append("=" * 70)
                logger.info("\n".join(lines))

                last_full_report = current_time


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments. CLI args override config file values."""
    parser = argparse.ArgumentParser(description="Realistic stress test for a Streamlit chatbot application.")
    parser.add_argument(
        "-c",
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the JSON config file (default: config.json next to this script).",
    )
    parser.add_argument(
        "-u",
        "--url",
        default=None,
        help="Target application URL (overrides config).",
    )
    parser.add_argument(
        "-n",
        "--users",
        type=int,
        default=None,
        help="Number of concurrent simulated users (overrides config).",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=int,
        default=None,
        help="Test duration in seconds, 0 for unlimited (overrides config).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging (shows exploration/reading/pause details).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)

    # CLI args override config file values
    if args.url is not None:
        config["app_url"] = args.url
    if args.users is not None:
        config["num_users"] = args.users
    if args.duration is not None:
        config["test_duration"] = args.duration

    app_url = config["app_url"]
    num_users = config["num_users"]
    test_duration = config["test_duration"]
    behavior = config["behavior"]

    collector = MetricsCollector(config)

    header = "\n".join(
        [
            "",
            "=" * 70,
            "STREAMLIT REALISTIC STRESS TEST",
            "=" * 70,
            f"Config file:          {args.config}",
            f"Target URL:           {app_url}",
            f"Concurrent Users:     {num_users}",
            f"Duration:             {test_duration}s ({test_duration // 60}min)",
            f"Questions loaded:     {len(config['questions'])}",
            "",
            "User Behavior:",
            f"   Initial exploration:    {behavior['initial_page_exploration'][0]}-{behavior['initial_page_exploration'][1]}s",
            f"   Reading responses:      {behavior['reading_response'][0]}-{behavior['reading_response'][1]}s",
            f"   Between questions:      {behavior['between_questions'][0]}-{behavior['between_questions'][1]}s",
            f"   Questions per session:  {behavior['questions_per_session'][0]}-{behavior['questions_per_session'][1]}",
            "",
            "Reports every 60 seconds",
            "=" * 70,
        ]
    )
    logger.info(header)

    stop_event = threading.Event()

    # Start the statistics reporting thread
    stats_thread = threading.Thread(target=print_live_stats, args=(collector,), daemon=True)
    stats_thread.start()

    # Start simulated users
    user_threads = []
    for i in range(num_users):
        t = threading.Thread(target=realistic_user_session, args=(i, stop_event, config, collector))
        t.start()
        user_threads.append(t)
        time.sleep(random.uniform(1, 5))  # Stagger user starts

    try:
        if test_duration > 0:
            logger.info("Test will run for %d minutes...", test_duration // 60)
            deadline = time.time() + test_duration
            while time.time() < deadline:
                if collector.active_users == 0 and all(not t.is_alive() for t in user_threads):
                    logger.info("All users finished early - wrapping up...")
                    break
                time.sleep(1)
            else:
                logger.info("Test duration reached - stopping users...")
        else:
            logger.info("Press Ctrl+C to stop")
            while True:
                if collector.active_users == 0 and all(not t.is_alive() for t in user_threads):
                    logger.info("All users finished - wrapping up...")
                    break
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Stopping test...")

    finally:
        stop_event.set()

        logger.info("Waiting for users to finish...")
        for t in user_threads:
            t.join(timeout=5)

        # Final statistics
        final_stats = collector.get_stats()
        if final_stats:
            elapsed_min = final_stats["elapsed_time"] / 60
            lines = [
                "",
                "=" * 70,
                "FINAL STATISTICS",
                "=" * 70,
                f"  Total duration:       {elapsed_min:.1f} min",
                f"  Completed sessions:   {final_stats['completed_sessions']}",
                f"  Failed sessions:      {final_stats['failed_sessions']}",
                f"  Total questions:      {final_stats['total_questions']}",
            ]

            if final_stats["total_questions"] > 0:
                qpm = (final_stats["total_questions"] / final_stats["elapsed_time"]) * 60
                lines.append(f"  Avg questions/min:    {qpm:.2f}")

            lines += [
                "",
                "  RESPONSE TIMES:",
                f"   Average:             {final_stats['avg_query_time']:.2f}s",
                f"   Min:                 {final_stats['min_query_time']:.2f}s",
                f"   Max:                 {final_stats['max_query_time']:.2f}s",
                f"   P95:                 {final_stats['p95_query_time']:.2f}s",
            ]

            success_rate = (
                final_stats["total_questions"] / (final_stats["total_questions"] + final_stats["failed_sessions"]) * 100
                if final_stats["total_questions"] > 0
                else 0
            )
            lines.append("")
            lines.append(f"  Success rate:         {success_rate:.1f}%")
            lines.append("=" * 70)
            logger.info("\n".join(lines))

        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realistic_stress_test_{timestamp}.json"
        collector.save_to_file(filename)


if __name__ == "__main__":
    main()
