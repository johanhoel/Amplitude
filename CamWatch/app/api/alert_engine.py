"""Alert rules engine — evaluates rules against new events."""
import os, json, time, threading
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.environ.get('DATA_PATH', '/data'))


class AlertRuleEngine:
    def __init__(self):
        self.rules = []
        self._load_rules()
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def _load_rules(self):
        rules_file = DATA_DIR / 'alert_rules.json'
        try:
            raw = json.loads(rules_file.read_text()) if rules_file.exists() else []
            self.rules = [r for r in raw if r.get('enabled', True)]
        except (json.JSONDecodeError, FileNotFoundError):
            self.rules = []

    def reload_rules(self):
        with self._lock:
            self._load_rules()

    def evaluate_event(self, event_data):
        matched = []
        with self._lock:
            for rule in self.rules:
                if not rule.get('enabled', True):
                    continue
                if self._rule_matches(rule, event_data):
                    matched.append(rule['id'])
        for rule_id in matched:
            self._execute_actions(rule_id, event_data)
        return matched

    def _rule_matches(self, rule, event_data):
        conditions = rule.get('conditions', {})
        # Time window check
        tw = conditions.get('time_window')
        if tw:
            from_h, from_m = map(int, tw.get('from','00:00').split(':'))
            to_h, to_m = map(int, tw.get('to','23:59').split(':'))
            now_min = datetime.now().hour * 60 + datetime.now().minute
            from_min = from_h * 60 + from_m
            to_min = to_h * 60 + to_m
            if from_min <= to_min:
                in_window = from_min <= now_min < to_min
            else:
                in_window = now_min >= from_min or now_min < to_min
            if not in_window: return False

        # Days of week check
        dow = conditions.get('days_of_week')
        if dow:
            day_names = ['mon','tue','wed','thu','fri','sat','sun']
            today = datetime.now().strftime('%a').lower()
            if today not in dow: return False

        # Camera check
        rule_cams = conditions.get('cameras')
        if rule_cams and event_data.get('camera'):
            if event_data['camera'] not in rule_cams: return False

        # Object type check
        rule_objs = conditions.get('objects')
        if rule_objs and event_data.get('labels'):
            labels = list(event_data['labels'].keys())
            if not any(o in labels for o in rule_objs): return False

        # Person name filter
        person_filter = conditions.get('person')
        if person_filter:
            known = [f.get('name','') for f in event_data.get('known', [])]
            plates = [p.get('name','') or p.get('plate','') for p in event_data.get('plates', [])]
            all_names = known + plates
            if not any(person_filter.lower() in n.lower() for n in all_names if n): return False

        # Cooldown check
        rule_id = rule.get('id')
        fires_file = DATA_DIR / 'alert_fires.json'
        try:
            fires = json.loads(fires_file.read_text()) if fires_file.exists() else {}
            last_fire = fires.get(rule_id)
            cooldown = rule.get('cooldown_seconds', 300)
            if last_fire and (time.time() - last_fire) < cooldown: return False
        except Exception: pass

        return True

    def _execute_actions(self, rule_id, event_data):
        actions = {}
        with self._lock:
            for rule in self.rules:
                if rule.get('id') == rule_id:
                    actions = rule.get('actions', {})
                    break
        # Record fire time
        fires_file = DATA_DIR / 'alert_fires.json'
        try:
            fires = json.loads(fires_file.read_text()) if fires_file.exists() else {}
            fires[rule_id] = time.time()
            tmp = fires_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(fires))
            tmp.replace(fires_file)
        except Exception: pass

        # Webhook
        webhook_url = actions.get('webhook_url')
        if webhook_url:
            try:
                import urllib.request
                data = json.dumps(event_data).encode()
                req = urllib.request.Request(webhook_url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=10) as resp: pass
            except Exception: pass

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try: self.reload_rules()
            except Exception: pass
            time.sleep(60)


alert_engine = AlertRuleEngine()
