"""v8.4: ephemeral loopback OTLP diagnostic tests (no real Codex claims)."""
import json
import sys
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import codex_otel_probe as probe  # noqa: E402


class ProbeTests(unittest.TestCase):
    def test_skill_event_and_unknown_without_positive_event(self):
        payload = {"resourceLogs": [{"scopeLogs": [{"logRecords": [
            {"body": {"stringValue": "codex.skill_invocation"},
             "attributes": [
                 {"key": "skill.name",
                  "value": {"stringValue": "project-skill-architect"}},
                 {"key": "skill.invocation_type",
                  "value": {"stringValue": "implicit"}},
             ]},
            {"body": {"stringValue": "codex.tool_result"}, "attributes": []},
        ]}]}]}
        self.assertEqual(probe.summarize(payload), {
            "records": 2, "skill_events": 1, "psa_events": 1,
            "other_skill_events": 0, "implicit_psa_events": 1,
            "explicit_psa_events": 0,
        })
        self.assertEqual(probe.classification(0), "unknown")
        self.assertEqual(probe.classification(1), "invoke")

    def test_other_skill_does_not_count_as_psa(self):
        payload = {"resourceLogs": [{"scopeLogs": [{"logRecords": [
            {"eventName": "codex.skill_invocation", "attributes": [
                {"key": "skill.name",
                 "value": {"stringValue": "release-check"}},
            ]},
        ]}]}]}
        result = probe.summarize(payload)
        self.assertEqual(result["skill_events"], 1)
        self.assertEqual(result["psa_events"], 0)
        self.assertEqual(result["other_skill_events"], 1)

    def test_rejects_invalid_http_input_without_retention(self):
        server = probe.make_server(0)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]

            def post(path, body, content_type="application/json"):
                conn = HTTPConnection("127.0.0.1", port, timeout=2)
                conn.request("POST", path, body, headers={"Content-Type": content_type})
                response = conn.getresponse()
                status = response.status
                response.read()
                conn.close()
                return status

            self.assertEqual(post("/v1/traces", b"{}"), 404)
            self.assertEqual(post("/v1/logs", b"{}", "text/plain"), 415)
            self.assertEqual(post("/v1/logs", b"bad-json"), 400)
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.putrequest("POST", "/v1/logs")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(probe.MAX_BODY_BYTES + 1))
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
            conn.close()
            self.assertEqual(server.totals["requests"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_counts_without_writing_raw_payloads(self):
        server = probe.make_server(0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = json.dumps({"resourceLogs": [{"scopeLogs": [{
                "logRecords": [{
                    "body": {"stringValue": "codex.skill_invocation"},
                    "attributes": [{"key": "skill.name", "value": {
                        "stringValue": "project-skill-architect"}}],
                }],
            }]}]}).encode("utf-8")
            conn = HTTPConnection("127.0.0.1",
                                  server.server_address[1], timeout=2)
            conn.request("POST", "/v1/logs", payload,
                         headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            conn.close()
            self.assertEqual(server.totals["requests"], 1)
            self.assertEqual(server.totals["psa_events"], 1)
            self.assertFalse(hasattr(server, "raw_payloads"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
