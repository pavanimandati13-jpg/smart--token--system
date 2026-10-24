"""Smart Queue Token System - backend.

Pure Python standard library (http.server + sqlite3). No installs needed.
Run:  python app.py      then open http://127.0.0.1:8000
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import webbrowser
import mimetypes
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "queue.db")
STATIC = os.path.realpath(os.path.join(BASE, "static"))
FMT = "%Y-%m-%d %H:%M:%S"
LOCK = threading.Lock()

# ---- Smart scheduling settings -------------------------------------------
PRIORITY = {"normal": 1, "senior": 2, "disabled": 2, "emergency": 3}
PRIORITY_WEIGHT = 15      # each priority level is worth 15 "waiting minutes"
AGING_PER_MIN = 1.0       # every minute waited adds 1 point (prevents starvation)

DEFAULT_SERVICES = [
    ("General Enquiry", "G", 5),
    ("Billing & Payments", "B", 8),
    ("Documents", "D", 10),
    ("Customer Support", "S", 12),
]


class ApiError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status
        self.message = message


# ---- Database ---------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            prefix TEXT NOT NULL,
            avg_minutes REAL NOT NULL DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS tokens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL,
            service_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            called_at TEXT,
            completed_at TEXT,
            counter INTEGER,
            FOREIGN KEY(service_id) REFERENCES services(id)
        );
        """
    )
    if conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO services(name, prefix, avg_minutes) VALUES (?,?,?)",
            DEFAULT_SERVICES,
        )
    conn.commit()
    conn.close()


# ---- Smart queue logic --------------------------------------------------------
def parse_time(s):
    return datetime.strptime(s, FMT)


def score(row, now):
    """Higher score = served earlier. Priority + minutes already waited."""
    waited = (now - parse_time(row["created_at"])).total_seconds() / 60.0
    return PRIORITY.get(row["priority"], 1) * PRIORITY_WEIGHT + waited * AGING_PER_MIN


def waiting_sorted(conn, service_id, now):
    rows = conn.execute(
        "SELECT * FROM tokens WHERE service_id=? AND status='waiting'", (service_id,)
    ).fetchall()
    return sorted(rows, key=lambda r: (-score(r, now), r["id"]))


def avg_service_minutes(conn, service_id):
    """Smoothed average of the last 10 real service durations."""
    default = conn.execute(
        "SELECT avg_minutes FROM services WHERE id=?", (service_id,)
    ).fetchone()["avg_minutes"]
    rows = conn.execute(
        "SELECT called_at, completed_at FROM tokens WHERE service_id=? AND status='completed' "
        "AND called_at IS NOT NULL AND completed_at IS NOT NULL ORDER BY id DESC LIMIT 10",
        (service_id,),
    ).fetchall()
    durations = [
        (parse_time(r["completed_at"]) - parse_time(r["called_at"])).total_seconds() / 60.0
        for r in rows
    ]
    return (sum(durations) + 2 * default) / (len(durations) + 2)


def active_counters(conn, service_id, now):
    since = (now - timedelta(minutes=30)).strftime(FMT)
    n = conn.execute(
        "SELECT COUNT(DISTINCT counter) FROM tokens WHERE service_id=? AND counter IS NOT NULL "
        "AND called_at>=?",
        (service_id, since),
    ).fetchone()[0]
    return max(1, n)


def fetch_token(conn, token_id):
    return conn.execute(
        "SELECT t.*, s.name AS service_name, s.prefix AS prefix FROM tokens t "
        "JOIN services s ON s.id=t.service_id WHERE t.id=?",
        (token_id,),
    ).fetchone()


def token_view(conn, row, now):
    d = {
        "id": row["id"],
        "number": row["number"],
        "service_id": row["service_id"],
        "service_name": row["service_name"],
        "name": row["name"],
        "priority": row["priority"],
        "status": row["status"],
        "created_at": row["created_at"],
        "called_at": row["called_at"],
        "completed_at": row["completed_at"],
        "counter": row["counter"],
    }
    if row["status"] == "waiting":
        queue = waiting_sorted(conn, row["service_id"], now)
        ids = [r["id"] for r in queue]
        position = ids.index(row["id"]) + 1 if row["id"] in ids else 1
        ahead = position - 1
        avg = avg_service_minutes(conn, row["service_id"])
        counters = active_counters(conn, row["service_id"], now)
        d["position"] = position
        d["ahead"] = ahead
        d["eta_minutes"] = int(round(ahead * avg / counters))
    return d


# ---- API actions ----------------------------------------------------------------
def to_int(value, field):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Invalid " + field)


def issue_token(conn, body, now):
    service_id = to_int(body.get("service_id"), "service")
    service = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    if not service:
        raise ApiError(404, "Service not found")
    priority = str(body.get("priority") or "normal").lower()
    if priority not in PRIORITY:
        raise ApiError(400, "Invalid priority")
    name = str(body.get("name") or "").strip()[:60] or "Guest"
    phone = str(body.get("phone") or "").strip()[:20]
    today = now.strftime("%Y-%m-%d")
    seq = conn.execute(
        "SELECT COUNT(*) FROM tokens WHERE service_id=? AND substr(created_at,1,10)=?",
        (service_id, today),
    ).fetchone()[0] + 1
    number = "%s%03d" % (service["prefix"], seq)
    cur = conn.execute(
        "INSERT INTO tokens(number, service_id, name, phone, priority, status, created_at) "
        "VALUES (?,?,?,?,?,'waiting',?)",
        (number, service_id, name, phone, priority, now.strftime(FMT)),
    )
    return token_view(conn, fetch_token(conn, cur.lastrowid), now)


def call_next(conn, body, now):
    service_id = to_int(body.get("service_id"), "service")
    counter = to_int(body.get("counter"), "counter")
    if counter < 1 or counter > 99:
        raise ApiError(400, "Counter must be between 1 and 99")
    busy = conn.execute(
        "SELECT number FROM tokens WHERE status='serving' AND counter=?", (counter,)
    ).fetchone()
    if busy:
        raise ApiError(409, "Counter %d is still serving %s. Complete or skip it first." % (counter, busy["number"]))
    queue = waiting_sorted(conn, service_id, now)
    if not queue:
        raise ApiError(404, "No tokens waiting for this service")
    chosen = queue[0]
    conn.execute(
        "UPDATE tokens SET status='serving', called_at=?, counter=? WHERE id=?",
        (now.strftime(FMT), counter, chosen["id"]),
    )
    return token_view(conn, fetch_token(conn, chosen["id"]), now)


def change_status(conn, token_id, action, now):
    row = fetch_token(conn, token_id)
    if not row:
        raise ApiError(404, "Token not found")
    status = row["status"]
    if action == "complete":
        if status != "serving":
            raise ApiError(409, "Only a token being served can be completed")
        conn.execute("UPDATE tokens SET status='completed', completed_at=? WHERE id=?",
                     (now.strftime(FMT), token_id))
    elif action == "skip":
        if status not in ("serving", "waiting"):
            raise ApiError(409, "Token is already closed")
        conn.execute("UPDATE tokens SET status='skipped', completed_at=? WHERE id=?",
                     (now.strftime(FMT), token_id))
    elif action == "cancel":
        if status != "waiting":
            raise ApiError(409, "Only a waiting token can be cancelled")
        conn.execute("UPDATE tokens SET status='cancelled', completed_at=? WHERE id=?",
                     (now.strftime(FMT), token_id))
    else:
        raise ApiError(404, "Unknown action")
    return token_view(conn, fetch_token(conn, token_id), now)


def queue_list(conn, service_id, now):
    avg = avg_service_minutes(conn, service_id)
    counters = active_counters(conn, service_id, now)
    out = []
    for i, r in enumerate(waiting_sorted(conn, service_id, now)):
        out.append({
            "id": r["id"], "number": r["number"], "name": r["name"],
            "priority": r["priority"], "position": i + 1,
            "waited_minutes": round((now - parse_time(r["created_at"])).total_seconds() / 60.0, 1),
            "eta_minutes": int(round(i * avg / counters)),
        })
    return out


def board(conn, now):
    today = now.strftime("%Y-%m-%d")
    services = []
    for s in conn.execute("SELECT * FROM services ORDER BY id").fetchall():
        waiting = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE service_id=? AND status='waiting'", (s["id"],)
        ).fetchone()[0]
        serving = conn.execute(
            "SELECT number, counter FROM tokens WHERE service_id=? AND status='serving' ORDER BY counter",
            (s["id"],),
        ).fetchall()
        services.append({
            "id": s["id"], "name": s["name"], "prefix": s["prefix"], "waiting": waiting,
            "serving": [{"number": r["number"], "counter": r["counter"]} for r in serving],
        })
    recent = conn.execute(
        "SELECT id, number, counter, called_at FROM tokens WHERE called_at IS NOT NULL "
        "AND substr(called_at,1,10)=? ORDER BY called_at DESC, id DESC LIMIT 6", (today,)
    ).fetchall()
    return {"services": services, "recent": [dict(r) for r in recent]}


def stats(conn, now):
    today = now.strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT t.*, s.name AS service_name FROM tokens t JOIN services s ON s.id=t.service_id "
        "WHERE substr(t.created_at,1,10)=?", (today,)
    ).fetchall()

    def mean(values):
        return round(sum(values) / len(values), 1) if values else 0

    waits = [(parse_time(r["called_at"]) - parse_time(r["created_at"])).total_seconds() / 60.0
             for r in rows if r["called_at"]]
    svc = [(parse_time(r["completed_at"]) - parse_time(r["called_at"])).total_seconds() / 60.0
           for r in rows if r["status"] == "completed" and r["called_at"] and r["completed_at"]]
    count = lambda st: len([r for r in rows if r["status"] == st])
    per_service = {}
    for r in rows:
        per_service[r["service_name"]] = per_service.get(r["service_name"], 0) + 1
    return {
        "issued": len(rows), "waiting": count("waiting"), "serving": count("serving"),
        "completed": count("completed"), "skipped": count("skipped"),
        "cancelled": count("cancelled"),
        "avg_wait_minutes": mean(waits), "avg_service_minutes": mean(svc),
        "per_service": per_service,
    }


def handle(conn, method, path, q, body):
    """Return (status_code, json_data)."""
    now = datetime.now().replace(microsecond=0)
    if method == "GET":
        if path == "/api/services":
            return 200, [dict(r) for r in conn.execute("SELECT * FROM services ORDER BY id")]
        if path == "/api/board":
            return 200, board(conn, now)
        if path == "/api/stats":
            return 200, stats(conn, now)
        if path == "/api/queue":
            return 200, queue_list(conn, to_int(q.get("service_id"), "service"), now)
        if path == "/api/tokens/lookup":
            number = str(q.get("number") or "").strip().upper()
            row = conn.execute("SELECT id FROM tokens WHERE number=? ORDER BY id DESC LIMIT 1",
                               (number,)).fetchone()
            if not row:
                raise ApiError(404, "Token %s not found" % (number or "(empty)"))
            return 200, token_view(conn, fetch_token(conn, row["id"]), now)
        m = re.match(r"^/api/tokens/(\d+)$", path)
        if m:
            row = fetch_token(conn, int(m.group(1)))
            if not row:
                raise ApiError(404, "Token not found")
            return 200, token_view(conn, row, now)
        m = re.match(r"^/api/counter/(\d+)$", path)
        if m:
            row = conn.execute("SELECT id FROM tokens WHERE status='serving' AND counter=? LIMIT 1",
                               (int(m.group(1)),)).fetchone()
            return 200, (token_view(conn, fetch_token(conn, row["id"]), now) if row else None)
    elif method == "POST":
        if path == "/api/tokens":
            return 201, issue_token(conn, body, now)
        if path == "/api/call":
            return 200, call_next(conn, body, now)
        m = re.match(r"^/api/tokens/(\d+)/(complete|skip|cancel)$", path)
        if m:
            return 200, change_status(conn, int(m.group(1)), m.group(2), now)
    raise ApiError(404, "Not found")


def run_api(method, path, q, body):
    with LOCK:
        conn = db()
        try:
            status, data = handle(conn, method, path, q, body)
            conn.commit()
            return status, data
        except ApiError:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---- HTTP server ----------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SmartQueue/1.0"

    def log_message(self, fmt, *args):
        if "/api/" not in (self.path or ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_bytes(self, status, payload, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def api(self, method):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        body = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self.send_json(400, {"error": "Invalid JSON"})
                if not isinstance(body, dict):
                    return self.send_json(400, {"error": "JSON object expected"})
        try:
            status, data = run_api(method, path, q, body)
            self.send_json(status, data)
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
        except Exception as e:  # never crash the server
            self.send_json(500, {"error": "Server error: %s" % e})

    def static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.realpath(os.path.join(STATIC, rel))
        if not full.startswith(STATIC + os.sep) or not os.path.isfile(full):
            return self.send_json(404, {"error": "Not found"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self.send_bytes(200, f.read(), ctype)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET")
        self.static(path)

    def do_POST(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self.api("POST")
        self.send_json(404, {"error": "Not found"})


def main():
    ap = argparse.ArgumentParser(description="Smart Queue Token System")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to allow other devices on your Wi-Fi")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    init_db()
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("Could not start on port %d: %s" % (args.port, e))
        print("Try another port:  python app.py --port 8080")
        sys.exit(1)

    url = "http://127.0.0.1:%d" % args.port
    print("Smart Queue Token System running at " + url)
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
