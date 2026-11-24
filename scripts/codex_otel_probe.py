#!/usr/bin/env python3
"""Temporary loopback-only Codex OTLP/HTTP JSON skill-invocation probe.

Diagnostic only: receives OTLP JSON in memory, discards raw payloads, and prints
bounded counters. Never use the absence of a skill event as proof of a skip.
Does not change Codex config, install hooks, or contact a third-party server.

Usage: python scripts/codex_otel_probe.py [--port 43181]
Stop with Ctrl+C after the Codex CLI exits and has flushed telemetry.
"""
from __future__ import annotations

import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from typing import Any

MAX_BODY_BYTES = 1_048_576
MAX_RECORDS_PER_BATCH = 4096
TARGET = "project-skill-architect"
KEYS = (
    "records", "skill_events", "psa_events", "other_skill_events",
    "implicit_psa_events", "explicit_psa_events",
)


def _value(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("stringValue", "value", "string_value"):
            raw = value.get(key)
            if isinstance(raw, str):
                return raw
    return None


def _attributes(record: dict[str, Any]) -> dict[str, str]:
    # Decode only the event fields required for counts.
    result: dict[str, str] = {}
    for item in record.get("attributes", []):
        if not isinstance(item, dict):
            continue
        name = item.get("key")
        if name not in ("skill.name", "skill_name", "skill.invocation_type",
                        "skill_invocation_type", "event.name", "event_name"):
            continue
        val = _value(item.get("value"))
        if val is not None:
            result[name] = val
    return result


def summarize(payload: Any) -> dict[str, int]:
    counts = {key: 0 for key in KEYS}
    if not isinstance(payload, dict):
        return counts
    for resource in payload.get("resourceLogs", []):
        if not isinstance(resource, dict):
            continue
        for scope in resource.get("scopeLogs", []):
            if not isinstance(scope, dict):
                continue
            for record in scope.get("logRecords", []):
                counts["records"] += 1
                if counts["records"] > MAX_RECORDS_PER_BATCH:
                    raise ValueError("Too many log records")
                if not isinstance(record, dict):
                    continue
                attrs = _attributes(record)
                name = (record.get("eventName") or record.get("event_name")
                        or _value(record.get("body")) or attrs.get("event.name")
                        or attrs.get("event_name"))
                if name != "codex.skill_invocation":
                    continue
                counts["skill_events"] += 1
                skill = attrs.get("skill.name") or attrs.get("skill_name")
                if skill == TARGET:
                    counts["psa_events"] += 1
                    mode = attrs.get("skill.invocation_type") or attrs.get(
                        "skill_invocation_type")
                    if mode == "implicit":
                        counts["implicit_psa_events"] += 1
                    elif mode == "explicit":
                        counts["explicit_psa_events"] += 1
                else:
                    counts["other_skill_events"] += 1
    return counts


def classification(psa_events: int) -> str:
    return "invoke" if psa_events > 0 else "unknown"


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, *args: Any) -> None:
        # Do not print URLs, headers, identifiers or request content.
        return

    def _respond(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self) -> None:
        if self.path != "/v1/logs":
            self._respond(404)
            return
        if self.headers.get("Content-Encoding", "identity").lower() != "identity":
            self._respond(415)
            return
        if (self.headers.get("Content-Type", "").split(";", 1)[0]
                .strip().lower() != "application/json"):
            self._respond(415)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            self._respond(400)
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._respond(413)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            observed = summarize(payload)
        except (UnicodeError, ValueError, TypeError, KeyError):
            self._respond(400)
            return
        self.server.totals["requests"] += 1
        for key in KEYS:
            self.server.totals[key] += observed[key]
        self._respond(200)
        print("BATCH: " + json.dumps({
            "requests": self.server.totals["requests"],
            "records": observed["records"],
            "psa_events": observed["psa_events"],
        }), flush=True)


class _Server(HTTPServer):
    def __init__(self, address: tuple[str, int]):
        super().__init__(address, _Handler)
        self.totals = {"requests": 0, **{key: 0 for key in KEYS}}


def make_server(port: int) -> _Server:
    return _Server(("127.0.0.1", port))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=43181)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port out of range")
    with make_server(args.port) as server:
        print("READY: http://127.0.0.1:"
              + str(server.server_address[1]) + "/v1/logs", flush=True)
        print("Diagnostic listener only. Run Codex in another terminal, "
              "then press Ctrl+C here.", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            result = dict(server.totals)
            result["psa_observed"] = classification(result["psa_events"])
            result["absence_is_skip_proof"] = False
            print("SUMMARY: " + json.dumps(result, sort_keys=True),
                  flush=True)


if __name__ == "__main__":
    main()
