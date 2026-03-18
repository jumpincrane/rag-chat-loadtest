# stress_test_standalone.py
import time
import random
import threading
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
import statistics


# Configuration
APP_URL = "http://localhost:8000/"
NUM_USERS = 1
TEST_DURATION = 600  # 10 minutes

QUESTIONS = [
    "Tell me about red wines with platinum awards",
    "What beers are available at Merano?",
    "Recommend a wine for grilled meat",
    "Show me organic wines from Italy",
    "What's in section A?",
]


# Realistic user behavior timings (in seconds)
BEHAVIOR = {
    'initial_page_exploration': (3, 8),
    'before_first_question': (2, 5),
    'reading_response': (25, 40),
    'between_questions': (5, 15),
    'menu_browsing': (3, 7),
    'questions_per_session': (2, 5),
}


class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
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
            if metric.get('success'):
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
            self.user_activities[user_id] = {
                'activity': activity,
                'timestamp': time.time()
            }
    
    def get_user_activities(self):
        """Return a snapshot of all user activities."""
        with self.lock:
            return dict(self.user_activities)
    
    def get_stats(self):
        with self.lock:
            if not self.metrics:
                return None
            
            query_times = [m['query_time'] for m in self.metrics if m.get('success') and 'query_time' in m]
            load_times = [m['load_time'] for m in self.metrics if m.get('success') and 'load_time' in m and m['load_time'] > 0]
            
            return {
                'total_questions': self.total_questions,
                'completed_sessions': self.completed_sessions,
                'failed_sessions': self.failed_sessions,
                'active_users': self.active_users,
                'avg_query_time': statistics.mean(query_times) if query_times else 0,
                'min_query_time': min(query_times) if query_times else 0,
                'max_query_time': max(query_times) if query_times else 0,
                'p95_query_time': statistics.quantiles(query_times, n=20)[18] if len(query_times) >= 20 else (max(query_times) if query_times else 0),
                'avg_load_time': statistics.mean(load_times) if load_times else 0,
                'elapsed_time': time.time() - self.start_time,
            }
    
    def get_last_minute_stats(self):
        """Return aggregated statistics from the last 60 seconds."""
        with self.lock:
            current_time = time.time()
            one_minute_ago = current_time - 60
            
            recent_metrics = [m for m in self.metrics 
                            if m.get('timestamp') and 
                            datetime.fromisoformat(m['timestamp']).timestamp() > one_minute_ago]
            
            if not recent_metrics:
                return None
            
            successful = [m for m in recent_metrics if m.get('success')]
            query_times = [m['query_time'] for m in successful if 'query_time' in m]
            
            return {
                'questions_last_minute': len(successful),
                'avg_response_time': statistics.mean(query_times) if query_times else 0,
                'failed_last_minute': len([m for m in recent_metrics if not m.get('success')]),
            }
    
    def save_to_file(self, filename='stress_test_results.json'):
        with self.lock:
            data = {
                'test_config': {
                    'app_url': APP_URL,
                    'num_users': NUM_USERS,
                    'test_duration': TEST_DURATION,
                    'behavior_settings': BEHAVIOR,
                    'start_time': datetime.fromtimestamp(self.start_time).isoformat()
                },
                'summary': self.get_stats(),
                'detailed_metrics': self.metrics
            }
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"\n[SAVE] Results saved to {filename}")


collector = MetricsCollector()


def realistic_user_session(user_id, stop_event):
    """Simulate a realistic user session with activity tracking."""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        try:
            collector.user_started()
            session_num = 0
            
            while not stop_event.is_set():
                session_num += 1
                print(f"[START] User {user_id} - Session {session_num} started")
                
                page = browser.new_page()
                
                try:
                    # Phase 1: Load the page
                    collector.update_user_activity(user_id, "Loading page")
                    start_load = time.time()
                    page.goto(APP_URL, wait_until="networkidle", timeout=30000)
                    load_time = time.time() - start_load
                    print(f"[OK] User {user_id} - Page loaded in {load_time:.2f}s")
                    
                    page.wait_for_selector("text=Wine Chatbot Assistant", timeout=10000)
                    
                    # Phase 2: Explore the interface
                    collector.update_user_activity(user_id, "Exploring interface")
                    exploration_time = random.uniform(*BEHAVIOR['initial_page_exploration'])
                    print(f"[EXPLORE] User {user_id} - Exploring ({exploration_time:.1f}s)")
                    if stop_event.wait(exploration_time):
                        break
                    
                    # Randomly browse the Prompt Guide
                    if random.random() < 0.3:
                        collector.update_user_activity(user_id, "Browsing Prompt Guide")
                        print(f"[BROWSE] User {user_id} - Browsing Prompt Guide")
                        browse_time = random.uniform(*BEHAVIOR['menu_browsing'])
                        if stop_event.wait(browse_time):
                            break
                    
                    # Phase 3: Ask questions
                    num_questions = random.randint(*BEHAVIOR['questions_per_session'])
                    print(f"[PLAN] User {user_id} - Will ask {num_questions} questions")
                    
                    for q_num in range(1, num_questions + 1):
                        if stop_event.is_set():
                            break
                        
                        # Pause before asking
                        if q_num == 1:
                            collector.update_user_activity(user_id, "Thinking what to ask")
                            thinking_time = random.uniform(*BEHAVIOR['before_first_question'])
                            print(f"[THINK] User {user_id} - Thinking ({thinking_time:.1f}s)")
                            if stop_event.wait(thinking_time):
                                break
                        else:
                            collector.update_user_activity(user_id, "Pause between questions")
                            between_time = random.uniform(*BEHAVIOR['between_questions'])
                            print(f"[PAUSE] User {user_id} - Pause ({between_time:.1f}s)")
                            if stop_event.wait(between_time):
                                break
                        
                        chat_input = page.get_by_placeholder("Enter your question...")
                        question = random.choice(QUESTIONS)
                        
                        collector.update_user_activity(user_id, f"Typing question {q_num}/{num_questions}")
                        print(f"[TYPE] User {user_id} Q{q_num}/{num_questions} - Typing: {question[:40]}...")
                        
                        chat_input.click()
                        time.sleep(random.uniform(0.3, 0.8))
                        chat_input.fill(question)
                        time.sleep(random.uniform(0.2, 0.5))
                        
                        collector.update_user_activity(user_id, f"Waiting for response {q_num}/{num_questions}")
                        start_query = time.time()
                        chat_input.press("Enter")
                        print(f"[SEND] User {user_id} Q{q_num}/{num_questions} - Sent, waiting...")
                        
                        try:
                            page.wait_for_selector("text=Searching for information", timeout=5000)
                            print(f"[WAIT] User {user_id} Q{q_num}/{num_questions} - LLM processing...")
                        except:
                            pass
                        
                        try:
                            page.wait_for_selector(
                                "text=Searching for information",
                                state="detached",
                                timeout=60000
                            )
                            
                            query_time = time.time() - start_query
                            print(f"[OK] User {user_id} Q{q_num}/{num_questions} - Response in {query_time:.2f}s")
                            
                            collector.add_metric({
                                'user_id': user_id,
                                'session_num': session_num,
                                'question_num': q_num,
                                'question': question,
                                'load_time': load_time if q_num == 1 else 0,
                                'query_time': query_time,
                                'timestamp': datetime.now().isoformat(),
                                'success': True
                            })
                            
                            # Phase 4: Read the response
                            collector.update_user_activity(user_id, f"Reading response {q_num}/{num_questions}")
                            reading_time = random.uniform(*BEHAVIOR['reading_response'])
                            print(f"[READ] User {user_id} Q{q_num}/{num_questions} - Reading ({reading_time:.1f}s)")
                            
                            if stop_event.wait(reading_time):
                                break
                            
                        except Exception as e:
                            query_time = time.time() - start_query
                            print(f"[ERROR] User {user_id} Q{q_num}/{num_questions} - Error after {query_time:.2f}s")
                            
                            collector.add_metric({
                                'user_id': user_id,
                                'session_num': session_num,
                                'question_num': q_num,
                                'question': question,
                                'error': str(e),
                                'timestamp': datetime.now().isoformat(),
                                'success': False
                            })
                            break
                    
                    print(f"[DONE] User {user_id} - Session {session_num} completed")
                    page.close()
                    
                    # Decide whether to start a new session
                    if random.random() < 0.4:
                        collector.update_user_activity(user_id, "Waiting to start new session")
                        reset_wait = random.uniform(10, 30)
                        print(f"[RESTART] User {user_id} - New session in {reset_wait:.1f}s")
                        if stop_event.wait(reset_wait):
                            break
                    else:
                        print(f"[LEAVE] User {user_id} - Leaving")
                        break
                
                except Exception as e:
                    print(f"[ERROR] User {user_id} Session {session_num} - Error: {e}")
                    collector.add_metric({
                        'user_id': user_id,
                        'session_num': session_num,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat(),
                        'success': False
                    })
                    break
            
            collector.user_finished(success=True)
            collector.update_user_activity(user_id, "Finished")
            print(f"[END] User {user_id} - Finished ({session_num} sessions)")
            
        except Exception as e:
            print(f"[FATAL] User {user_id} - Fatal error: {e}")
            collector.user_finished(success=False)
        
        finally:
            browser.close()


def print_live_stats():
    """Print live statistics every 60 seconds."""
    last_full_report = time.time()
    
    while True:
        time.sleep(10)  # Check every 10 seconds
        
        current_time = time.time()
        
        # Co minutę: pełny raport
        if current_time - last_full_report >= 60:
            stats = collector.get_stats()
            last_min_stats = collector.get_last_minute_stats()
            
            if stats:
                print("\n" + "="*70)
                print(f"LIVE STATISTICS - {datetime.now().strftime('%H:%M:%S')}")
                print("="*70)
                
                elapsed_min = stats['elapsed_time'] / 60
                print(f"  Elapsed:              {int(elapsed_min)} min {int(stats['elapsed_time'] % 60)} sec")
                print(f"  Active users:         {stats['active_users']}")
                print(f"  Completed sessions:   {stats['completed_sessions']}")
                print(f"  Failed sessions:      {stats['failed_sessions']}")
                print(f"  Total questions:      {stats['total_questions']}")
                
                if stats['total_questions'] > 0:
                    qpm = (stats['total_questions'] / stats['elapsed_time']) * 60
                    print(f"  Avg questions/min:    {qpm:.2f}")
                
                print(f"\n  OVERALL RESPONSE TIMES:")
                print(f"   Average:             {stats['avg_query_time']:.2f}s")
                print(f"   Min:                 {stats['min_query_time']:.2f}s")
                print(f"   Max:                 {stats['max_query_time']:.2f}s")
                print(f"   P95:                 {stats['p95_query_time']:.2f}s")
                
                if stats['avg_load_time'] > 0:
                    print(f"\n  PAGE LOAD:")
                    print(f"   Average:             {stats['avg_load_time']:.2f}s")
                
                # Last minute statistics
                if last_min_stats:
                    print(f"\n  LAST MINUTE:")
                    print(f"   Questions:           {last_min_stats['questions_last_minute']}")
                    print(f"   Avg response:        {last_min_stats['avg_response_time']:.2f}s")
                    print(f"   Failed:              {last_min_stats['failed_last_minute']}")
                
                # Per-user activity breakdown
                activities = collector.get_user_activities()
                if activities:
                    print(f"\n  USER ACTIVITIES:")
                    for user_id, activity_info in sorted(activities.items()):
                        activity = activity_info['activity']
                        age = int(current_time - activity_info['timestamp'])
                        print(f"   User {user_id:2d}: {activity:40s} ({age}s ago)")
                
                print("="*70 + "\n")
                
                last_full_report = current_time


def main():
    print("\n" + "="*70)
    print("STREAMLIT REALISTIC STRESS TEST")
    print("="*70)
    print(f"Target URL:           {APP_URL}")
    print(f"Concurrent Users:     {NUM_USERS}")
    print(f"Duration:             {TEST_DURATION}s ({TEST_DURATION//60}min)")
    print(f"\nUser Behavior:")
    print(f"   Initial exploration:    {BEHAVIOR['initial_page_exploration'][0]}-{BEHAVIOR['initial_page_exploration'][1]}s")
    print(f"   Reading responses:      {BEHAVIOR['reading_response'][0]}-{BEHAVIOR['reading_response'][1]}s")
    print(f"   Between questions:      {BEHAVIOR['between_questions'][0]}-{BEHAVIOR['between_questions'][1]}s")
    print(f"   Questions per session:  {BEHAVIOR['questions_per_session'][0]}-{BEHAVIOR['questions_per_session'][1]}")
    print(f"\nReports every 60 seconds")
    print("="*70 + "\n")
    
    stop_event = threading.Event()
    
    # Start the statistics reporting thread
    stats_thread = threading.Thread(target=print_live_stats, daemon=True)
    stats_thread.start()
    
    # Start simulated users
    user_threads = []
    for i in range(NUM_USERS):
        t = threading.Thread(target=realistic_user_session, args=(i, stop_event))
        t.start()
        user_threads.append(t)
        time.sleep(random.uniform(1, 5))  # Stagger user starts
    
    try:
        if TEST_DURATION > 0:
            print(f"Test will run for {TEST_DURATION//60} minutes...\n")
            time.sleep(TEST_DURATION)
            print("\nTest duration reached - stopping users...")
        else:
            print("\nPress Ctrl+C to stop\n")
            while True:
                time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\nStopping test...")
    
    finally:
        stop_event.set()
        
        print("Waiting for users to finish...")
        for t in user_threads:
            t.join(timeout=30)
        
        # Final statistics
        final_stats = collector.get_stats()
        if final_stats:
            print("\n" + "="*70)
            print("FINAL STATISTICS")
            print("="*70)
            elapsed_min = final_stats['elapsed_time'] / 60
            print(f"  Total duration:       {elapsed_min:.1f} min")
            print(f"  Completed sessions:   {final_stats['completed_sessions']}")
            print(f"  Failed sessions:      {final_stats['failed_sessions']}")
            print(f"  Total questions:      {final_stats['total_questions']}")
            
            if final_stats['total_questions'] > 0:
                qpm = (final_stats['total_questions'] / final_stats['elapsed_time']) * 60
                print(f"  Avg questions/min:    {qpm:.2f}")
            
            print(f"\n  RESPONSE TIMES:")
            print(f"   Average:             {final_stats['avg_query_time']:.2f}s")
            print(f"   Min:                 {final_stats['min_query_time']:.2f}s")
            print(f"   Max:                 {final_stats['max_query_time']:.2f}s")
            print(f"   P95:                 {final_stats['p95_query_time']:.2f}s")
            
            success_rate = (final_stats['total_questions'] / 
                          (final_stats['total_questions'] + final_stats['failed_sessions']) * 100 
                          if final_stats['total_questions'] > 0 else 0)
            print(f"\n  Success rate:         {success_rate:.1f}%")
            print("="*70 + "\n")
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realistic_stress_test_{timestamp}.json"
        collector.save_to_file(filename)


if __name__ == "__main__":
    main()
