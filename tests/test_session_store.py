"""The online memory: the Upstash client (against a tiny fake server) and the 'fresh copy per request' behaviour."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from seating import session_store as ss


class _FakeUpstash(BaseHTTPRequestHandler):
    data: dict = {}
    seen_auth: list = []

    def do_POST(self):
        cmd = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen_auth.append(self.headers.get("Authorization"))
        if cmd[0] == "SET":
            type(self).data[cmd[1]] = cmd[2]
            assert cmd[3] == "EX" and int(cmd[4]) > 0
            out = {"result": "OK"}
        elif cmd[0] == "GET":
            out = {"result": type(self).data.get(cmd[1])}
        else:
            out = {"error": "unknown command"}
        body = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


class StoreClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeUpstash)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_round_trip_and_token(self):
        s = ss.RedisStore(self.url, "secret")
        self.assertIsNone(s.get("a" * 24))
        s.put("a" * 24, "héllo")
        self.assertEqual(s.get("a" * 24), "héllo")
        self.assertIn("Bearer secret", _FakeUpstash.seen_auth)

    def test_too_big_value_is_refused(self):
        with self.assertRaises(ss.StoreError):
            ss.RedisStore(self.url, "t").put("b" * 24, "x" * (ss.MAX_VALUE_BYTES + 1))

    def test_unreachable_store_raises_store_error(self):
        with self.assertRaises(ss.StoreError):
            ss.RedisStore("http://127.0.0.1:1", "t", timeout=1).get("c" * 24)

    def test_environment_variables(self):
        self.assertIsNone(ss.store_from_environment({}))
        self.assertIsNone(ss.store_from_environment({"KV_REST_API_URL": "https://x"}))      # token missing
        self.assertEqual(ss.store_from_environment({"KV_REST_API_URL": "https://x/", "KV_REST_API_TOKEN": "t"}).url, "https://x")
        self.assertEqual(ss.store_from_environment({"UPSTASH_REDIS_REST_URL": "https://y", "UPSTASH_REDIS_REST_TOKEN": "t"}).url, "https://y")

    def test_session_ids(self):
        a, b = ss.new_session_id(), ss.new_session_id()
        self.assertNotEqual(a, b)
        self.assertTrue(ss.valid_session_id(a))
        for bad in (None, "", "short", "x" * 100, "bad id with spaces!!!!!!"):
            self.assertFalse(ss.valid_session_id(bad))


class _DictStore:
    """Stands in for Upstash: a dict, so the API test needs no internet."""
    def __init__(self): self.d = {}
    def get(self, sid): return self.d.get(sid)
    def put(self, sid, value): self.d[sid] = value


try:
    from fastapi.testclient import TestClient
    import app as appmod
    HAVE_API = True
except ModuleNotFoundError:
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "fastapi is not installed")
class FreshCopyPerRequestTests(unittest.TestCase):
    """Each request starts from an EMPTY AppState (like Vercel's fresh copy); only the store carries data across."""

    def setUp(self):
        self.store = _DictStore()
        self._old = appmod.store
        appmod.store = self.store
        real_load = appmod.AppState.load
        self._real_load = real_load
        self.client = TestClient(appmod.app)

        def forgetful_load(inner, token):          # wipe everything first: proves the data came from the store
            inner.reset(); inner.benchmark_rows = None
            real_load(inner, token)
        appmod.AppState.load = forgetful_load

    def tearDown(self):
        appmod.store = self._old
        appmod.AppState.load = self._real_load

    def _sample(self, name):
        return open(appmod.SAMPLE / name, "rb")

    def test_data_survives_between_requests_and_downloads_work(self):
        c = self.client
        self.assertEqual(c.get("/api/data").status_code, 409)
        with self._sample("students.csv") as f:
            r = c.post("/api/data", files={"students": ("students.csv", f)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("seatwise_session", c.cookies)
        # a completely separate request still sees the students
        self.assertEqual(c.get("/api/data").status_code, 200)
        self.assertTrue(c.post("/api/timetable/reset").status_code == 200)
        plan = c.post("/api/plan", json={"rule": "fourway", "strategy": "hybrid"})
        self.assertEqual(plan.status_code, 200, plan.text)
        csv = c.get("/api/download/csv")                 # plan is rebuilt from the saved data
        self.assertEqual(csv.status_code, 200)
        self.assertIn("roll", csv.text.lower())

    def test_two_visitors_do_not_see_each_other(self):
        a, b = TestClient(appmod.app), TestClient(appmod.app)
        with self._sample("students.csv") as f:
            a.post("/api/data", files={"students": ("students.csv", f)})
        self.assertEqual(a.get("/api/data").status_code, 200)
        self.assertEqual(b.get("/api/data").status_code, 409)

    def test_store_failure_gives_a_clear_message(self):
        def boom(*a): raise ss.StoreError("down")
        self.store.get = boom
        self.client.cookies.set("seatwise_session", "z" * 24)
        r = self.client.get("/api/data")
        self.assertEqual(r.status_code, 503)
        self.assertIn("online memory", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()


class HealthCheckTests(unittest.TestCase):
    """/api/health tells the teacher (in plain words) whether the online memory works."""

    def setUp(self):
        import app as app_module
        from fastapi.testclient import TestClient
        self.app_module = app_module
        self.client = TestClient(app_module.app)
        self.old_store = app_module.store

    def tearDown(self):
        self.app_module.store = self.old_store

    def test_no_store_says_so(self):
        self.app_module.store = None
        body = self.client.get("/api/health").json()
        self.assertEqual((body["online_store"], body["working"]), (False, False))
        self.assertIn("Vercel", body["message"])

    def test_working_store(self):
        class Memory:
            def __init__(self): self.d = {}
            def get(self, k): return self.d.get(k)
            def put(self, k, v): self.d[k] = v
        self.app_module.store = Memory()
        body = self.client.get("/api/health").json()
        self.assertEqual((body["online_store"], body["working"]), (True, True))

    def test_broken_store(self):
        class Broken:
            def get(self, k): raise ss.StoreError("no connection")
            def put(self, k, v): raise ss.StoreError("no connection")
        self.app_module.store = Broken()
        body = self.client.get("/api/health").json()
        self.assertEqual((body["online_store"], body["working"]), (True, False))
        self.assertIn("no connection", body["message"])
