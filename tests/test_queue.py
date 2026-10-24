import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402


class QueueTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app.DB = self.path
        app.init_db()

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def call(self, method, path, body=None, q=None):
        return app.run_api(method, path, q or {}, body or {})

    def issue(self, name, priority="normal", service=1):
        return self.call("POST", "/api/tokens", {"name": name, "service_id": service, "priority": priority})[1]

    def test_numbering(self):
        self.assertEqual(self.issue("a")["number"], "G001")
        self.assertEqual(self.issue("b")["number"], "G002")
        self.assertEqual(self.issue("c", service=2)["number"], "B001")

    def test_priority_beats_normal(self):
        n = self.issue("normal")
        e = self.issue("e", priority="emergency")
        t = self.call("POST", "/api/call", {"service_id": 1, "counter": 1})[1]
        self.assertEqual(t["id"], e["id"])
        self.assertEqual(self.call("GET", "/api/tokens/%d" % n["id"])[1]["position"], 1)

    def test_aging_prevents_starvation(self):
        old = self.issue("old")
        self.issue("senior", priority="senior")
        old_time = (datetime.now() - timedelta(minutes=60)).strftime(app.FMT)
        conn = app.db()
        conn.execute("UPDATE tokens SET created_at=? WHERE id=?", (old_time, old["id"]))
        conn.commit()
        conn.close()
        t = self.call("POST", "/api/call", {"service_id": 1, "counter": 1})[1]
        self.assertEqual(t["id"], old["id"])

    def test_full_flow_and_stats(self):
        a = self.issue("a")
        t = self.call("POST", "/api/call", {"service_id": 1, "counter": 2})[1]
        self.assertEqual((t["status"], t["counter"]), ("serving", 2))
        with self.assertRaises(app.ApiError):  # counter busy
            self.call("POST", "/api/call", {"service_id": 1, "counter": 2})
        self.call("POST", "/api/tokens/%d/complete" % a["id"])
        s = self.call("GET", "/api/stats")[1]
        self.assertEqual((s["issued"], s["completed"], s["waiting"]), (1, 1, 0))

    def test_cancel_skip_and_errors(self):
        a = self.issue("a")
        self.call("POST", "/api/tokens/%d/cancel" % a["id"])
        with self.assertRaises(app.ApiError):
            self.call("POST", "/api/tokens/%d/cancel" % a["id"])
        with self.assertRaises(app.ApiError):  # nothing waiting
            self.call("POST", "/api/call", {"service_id": 1, "counter": 1})
        with self.assertRaises(app.ApiError):
            self.call("POST", "/api/tokens", {"service_id": 99})
        with self.assertRaises(app.ApiError):
            self.call("POST", "/api/tokens", {"service_id": 1, "priority": "vip"})

    def test_eta_and_lookup(self):
        self.issue("a")
        b = self.issue("b")
        v = self.call("GET", "/api/tokens/%d" % b["id"])[1]
        self.assertEqual((v["position"], v["ahead"]), (2, 1))
        self.assertGreater(v["eta_minutes"], 0)
        self.assertEqual(self.call("GET", "/api/tokens/lookup", q={"number": "g002"})[1]["id"], b["id"])


if __name__ == "__main__":
    unittest.main()
