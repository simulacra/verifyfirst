#!/usr/bin/env python3
"""
Integration tests for the verifyfirst MCP server.

These do not import server.py. They spawn it as a real subprocess and speak
real newline-delimited JSON-RPC 2.0 over its stdin/stdout, which is the only
thing an MCP client will ever do to it.

Run:  python3 test_server.py          (or: python3 -m unittest test_server -v)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
REGISTRY = os.path.join(HERE, "registry.json")

EXPECTED_TOOLS = {
    "list_instruments",
    "get_instrument",
    "blind_spots",
    "search",
    "get_entry",
    "from_symptom",
    "before_claiming",
    "get_protocol",
}


class Client:
    """A minimal MCP stdio client: spawn, write a line, read a line."""

    def __init__(self, args: list[str] | None = None) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, SERVER] + (args or []),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._id = 0

    def send_raw(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def read(self) -> dict:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise AssertionError(f"server closed stdout unexpectedly. stderr:\n{stderr}")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.send_raw(json.dumps(msg))
        return self.read()

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send_raw(json.dumps(msg))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def call_text(self, name: str, arguments: dict | None = None) -> str:
        resp = self.call_tool(name, arguments)
        assert "result" in resp, f"expected result, got {resp}"
        return resp["result"]["content"][0]["text"]

    def close(self) -> None:
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=5)
        finally:
            for stream in (self.proc.stdout, self.proc.stderr):
                if stream and not stream.closed:
                    stream.close()


class MCPTestCase(unittest.TestCase):
    """Base: one live server per test, handshake already done."""

    server_args: list[str] = []

    def setUp(self) -> None:
        self.client = Client(self.server_args)
        self.addCleanup(self.client.close)
        with open(REGISTRY, "r", encoding="utf-8") as fh:
            self.registry = json.load(fh)

    def handshake(self) -> dict:
        resp = self.client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-harness", "version": "1.0"},
            },
        )
        self.client.notify("notifications/initialized")
        return resp


class TestHandshake(MCPTestCase):
    def test_initialize_returns_serverinfo_and_protocol_version(self) -> None:
        resp = self.handshake()
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertNotIn("error", resp)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "verifyfirst")
        self.assertIn("tools", result["capabilities"])

    def test_unknown_protocol_version_falls_back_to_preferred(self) -> None:
        resp = self.client.request(
            "initialize", {"protocolVersion": "1999-01-01", "capabilities": {}}
        )
        self.assertEqual(resp["result"]["protocolVersion"], "2025-06-18")

    def test_initialized_notification_produces_no_response(self) -> None:
        self.handshake()
        # If the notification had wrongly produced a reply, the next request's
        # response would be off by one and this id check would fail.
        resp = self.client.request("ping")
        self.assertEqual(resp["id"], 2)
        self.assertEqual(resp["result"], {})

    def test_server_survives_unknown_notification(self) -> None:
        self.handshake()
        self.client.notify("notifications/cancelled", {"requestId": 99})
        resp = self.client.request("tools/list")
        self.assertIn("result", resp)


class TestToolsList(MCPTestCase):
    def test_lists_exactly_the_expected_tools(self) -> None:
        self.handshake()
        resp = self.client.request("tools/list")
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), len(EXPECTED_TOOLS))
        self.assertEqual({t["name"] for t in tools}, EXPECTED_TOOLS)

    def test_every_tool_has_a_substantive_description_and_schema(self) -> None:
        self.handshake()
        tools = self.client.request("tools/list")["result"]["tools"]
        for t in tools:
            with self.subTest(tool=t["name"]):
                self.assertGreater(
                    len(t["description"]), 80, "descriptions are what make a model call the tool"
                )
                self.assertEqual(t["inputSchema"]["type"], "object")

    def test_required_arguments_are_declared(self) -> None:
        self.handshake()
        tools = {t["name"]: t for t in self.client.request("tools/list")["result"]["tools"]}
        self.assertEqual(tools["blind_spots"]["inputSchema"]["required"], ["instrument"])
        self.assertEqual(tools["get_instrument"]["inputSchema"]["required"], ["id"])
        self.assertEqual(tools["search"]["inputSchema"]["required"], ["query"])
        self.assertEqual(tools["get_entry"]["inputSchema"]["required"], ["id"])
        self.assertNotIn("required", tools["get_protocol"]["inputSchema"])


class TestListInstruments(MCPTestCase):
    def test_returns_all_six_instrument_ids(self) -> None:
        self.handshake()
        text = self.client.call_text("list_instruments")
        ids = [i["id"] for i in self.registry["instruments"]]
        self.assertEqual(len(ids), 6)
        for iid in ids:
            self.assertIn(iid, text)

    def test_includes_name_and_used_when(self) -> None:
        self.handshake()
        text = self.client.call_text("list_instruments")
        for inst in self.registry["instruments"]:
            self.assertIn(inst["name"], text)
            self.assertIn(inst["used_when"], text)


class TestBlindSpots(MCPTestCase):
    def test_screenshot_blind_spots_match_registry_verbatim(self) -> None:
        self.handshake()
        text = self.client.call_text("blind_spots", {"instrument": "screenshot"})
        inst = next(i for i in self.registry["instruments"] if i["id"] == "screenshot")
        for blind in inst["blind_to"]:
            self.assertIn(blind, text)

    def test_is_terse_and_omits_full_entry_bodies(self) -> None:
        self.handshake()
        text = self.client.call_text("blind_spots", {"instrument": "exit-code"})
        self.assertNotIn("FALSE READING", text)
        self.assertLess(len(text), 1600, "blind_spots is a pre-flight check, not a dossier")

    def test_every_instrument_resolves(self) -> None:
        self.handshake()
        for inst in self.registry["instruments"]:
            with self.subTest(instrument=inst["id"]):
                text = self.client.call_text("blind_spots", {"instrument": inst["id"]})
                self.assertIn(inst["blind_to"][0], text)

    def test_loose_aliases_resolve(self) -> None:
        self.handshake()
        cases = {
            "curl": "http-response",
            "ps": "process-list",
            "journalctl": "log-output",
            "config": "file-on-disk",
            "EXIT_CODE": "exit-code",
            "the exit code of the command": "exit-code",
            "playwright": "screenshot",
        }
        for raw, expected in cases.items():
            with self.subTest(alias=raw):
                text = self.client.call_text("blind_spots", {"instrument": raw})
                self.assertTrue(
                    text.startswith(expected), f"{raw!r} resolved to: {text.splitlines()[0]}"
                )

    def test_unknown_instrument_is_a_tool_error_not_a_crash(self) -> None:
        self.handshake()
        resp = self.client.call_tool("blind_spots", {"instrument": "tea-leaves"})
        self.assertIn("result", resp)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("Unknown instrument", resp["result"]["content"][0]["text"])

    def test_missing_argument_is_a_tool_error(self) -> None:
        self.handshake()
        resp = self.client.call_tool("blind_spots", {})
        self.assertTrue(resp["result"]["isError"])


class TestGetInstrument(MCPTestCase):
    def test_full_detail_for_exit_code(self) -> None:
        self.handshake()
        text = self.client.call_text("get_instrument", {"id": "exit-code"})
        inst = next(i for i in self.registry["instruments"] if i["id"] == "exit-code")
        self.assertIn(inst["captures"], text)
        for blind in inst["blind_to"]:
            self.assertIn(blind, text)

    def test_includes_every_entry_for_that_instrument(self) -> None:
        self.handshake()
        for inst in self.registry["instruments"]:
            iid = inst["id"]
            expected = [e for e in self.registry["entries"] if e["instrument"] == iid]
            text = self.client.call_text("get_instrument", {"id": iid})
            with self.subTest(instrument=iid):
                for e in expected:
                    self.assertIn(e["id"], text)
                    self.assertIn(e["title"], text)
                    self.assertIn(e["discriminating_check"], text)
                # and no entries belonging to a different instrument
                for e in self.registry["entries"]:
                    if e["instrument"] != iid:
                        self.assertNotIn(e["title"], text)

    def test_unknown_id_is_a_tool_error(self) -> None:
        self.handshake()
        resp = self.client.call_tool("get_instrument", {"id": "seismograph"})
        self.assertTrue(resp["result"]["isError"])


class TestSearch(MCPTestCase):
    def _expected(self, needle: str) -> list[str]:
        n = needle.lower()
        return [
            e["id"]
            for e in self.registry["entries"]
            if n
            in " ".join(
                str(e.get(f, "")) for f in ("title", "false_reading", "true_state", "class")
            ).lower()
        ]

    def test_cache_query_matches_the_stale_observer_entry(self) -> None:
        self.handshake()
        text = self.client.call_text("search", {"query": "cache"})
        expected = self._expected("cache")
        self.assertIn("NS-007", expected)
        for eid in expected:
            self.assertIn(eid, text)

    def test_search_is_case_insensitive(self) -> None:
        self.handshake()
        lower = self.client.call_text("search", {"query": "canvas"})
        upper = self.client.call_text("search", {"query": "CANVAS"})
        mixed = self.client.call_text("search", {"query": "CaNvAs"})
        # The header echoes the query verbatim, so compare the matched ids.
        found = [
            {e["id"] for e in self.registry["entries"] if e["id"] in text}
            for text in (lower, upper, mixed)
        ]
        self.assertEqual(found[0], found[1])
        self.assertEqual(found[0], found[2])
        self.assertEqual(found[0], set(self._expected("canvas")))
        self.assertIn("NS-002", found[0])

    def test_matches_the_class_field(self) -> None:
        self.handshake()
        text = self.client.call_text("search", {"query": "observer-in-the-sample"})
        self.assertIn("NS-012", text)

    def test_no_match_returns_a_useful_message_not_an_error(self) -> None:
        self.handshake()
        resp = self.client.call_tool("search", {"query": "quantum-flux-capacitor"})
        self.assertFalse(resp["result"]["isError"])
        self.assertIn("No entries match", resp["result"]["content"][0]["text"])

    def test_broad_query_matches_many(self) -> None:
        self.handshake()
        text = self.client.call_text("search", {"query": "the"})
        expected = self._expected("the")
        self.assertGreaterEqual(len(expected), 10)
        for eid in expected:
            self.assertIn(eid, text)


class TestGetEntry(MCPTestCase):
    def test_ns_001_returns_the_right_record(self) -> None:
        self.handshake()
        text = self.client.call_text("get_entry", {"id": "NS-001"})
        e = next(x for x in self.registry["entries"] if x["id"] == "NS-001")
        self.assertIn(e["title"], text)
        self.assertIn(e["true_state"], text)
        self.assertIn(e["discriminating_check"], text)
        self.assertIn(e["why_blind"], text)

    def test_every_entry_id_is_retrievable(self) -> None:
        self.handshake()
        self.assertGreaterEqual(len(self.registry["entries"]), 14)
        for e in self.registry["entries"]:
            with self.subTest(entry=e["id"]):
                text = self.client.call_text("get_entry", {"id": e["id"]})
                self.assertIn(e["title"], text)

    def test_id_is_case_insensitive(self) -> None:
        self.handshake()
        self.assertEqual(
            self.client.call_text("get_entry", {"id": "ns-011"}),
            self.client.call_text("get_entry", {"id": "NS-011"}),
        )

    def test_unknown_entry_is_a_tool_error(self) -> None:
        self.handshake()
        resp = self.client.call_tool("get_entry", {"id": "NS-999"})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("No entry with id", resp["result"]["content"][0]["text"])


class TestGetProtocol(MCPTestCase):
    def test_returns_all_five_steps(self) -> None:
        self.handshake()
        text = self.client.call_text("get_protocol")
        for marker in ("1.", "2.", "3.", "4.", "5."):
            self.assertIn(marker, text)
        for phrase in (
            "Name the instrument",
            "cannot see",
            "could fail",
            "not the inference",
            "resolved values",
        ):
            self.assertIn(phrase, text)

    def test_includes_the_registry_principles(self) -> None:
        self.handshake()
        text = self.client.call_text("get_protocol")
        for p in self.registry["principles"]:
            self.assertIn(p["statement"], text)


class TestProtocolErrors(MCPTestCase):
    def test_unknown_tool_returns_jsonrpc_error(self) -> None:
        self.handshake()
        resp = self.client.call_tool("delete_everything", {})
        self.assertNotIn("result", resp)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("Unknown tool", resp["error"]["message"])
        self.assertIn("blind_spots", resp["error"]["data"]["available_tools"])

    def test_server_still_works_after_an_unknown_tool(self) -> None:
        self.handshake()
        self.client.call_tool("delete_everything", {})
        text = self.client.call_text("get_entry", {"id": "NS-005"})
        self.assertIn("enable --now", text)

    def test_unknown_method_returns_method_not_found(self) -> None:
        self.handshake()
        resp = self.client.request("tools/teleport")
        self.assertEqual(resp["error"]["code"], -32601)

    def test_malformed_json_returns_parse_error_and_server_survives(self) -> None:
        self.handshake()
        self.client.send_raw("{not json at all")
        resp = self.client.read()
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])
        follow_up = self.client.request("tools/list")
        self.assertEqual(len(follow_up["result"]["tools"]), len(EXPECTED_TOOLS))

    def test_tools_call_without_name_is_invalid_params(self) -> None:
        self.handshake()
        resp = self.client.request("tools/call", {"arguments": {}})
        self.assertEqual(resp["error"]["code"], -32602)

    def test_blank_lines_are_ignored(self) -> None:
        self.handshake()
        self.client.send_raw("")
        self.client.send_raw("   ")
        resp = self.client.request("ping")
        self.assertIn("result", resp)


class TestOfflineByDefault(unittest.TestCase):
    def test_no_network_call_without_remote_flag(self) -> None:
        """Bundled registry is the default source; stderr must say so."""
        proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            proc.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
                    }
                )
                + "\n"
            )
            proc.stdin.flush()
            resp = json.loads(proc.stdout.readline())
            self.assertEqual(resp["result"]["serverInfo"]["name"], "verifyfirst")
            _, stderr = proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream and not stream.closed:
                    stream.close()
        self.assertIn("bundled registry", stderr)
        self.assertNotIn("remote fetch", stderr)
        with open(REGISTRY, "r", encoding="utf-8") as fh:
            reg = json.load(fh)
        self.assertIn(
            f'{len(reg["instruments"])} instruments, '
            f'{len(reg["entries"])} entries, {len(EXPECTED_TOOLS)} tools',
            stderr,
        )


class TestFromSymptom(MCPTestCase):
    """The symptom-first entry point. Callers describe what they see in their
    own words, so these assert on real phrasings rather than on the exact
    strings in the registry."""

    def test_plain_descriptions_reach_the_right_symptom(self) -> None:
        self.handshake()
        cases = [
            ("I deployed but the site still shows the old version",
             "The deploy ran but nothing changed"),
            ("systemctl says active but requests fail",
             "The service says active but is not working"),
            ("my curl returns 200 but the json is wrong",
             "The API returned 200 but the data is wrong"),
            ("the script just hangs forever with no output",
             "A command hangs and never returns"),
            ("tests are green but the feature does not work",
             "The tests pass but the feature is broken"),
            ("clicking the button does nothing", "Clicks land on nothing"),
        ]
        for description, expected in cases:
            with self.subTest(description=description):
                text = self.client.call_text("from_symptom", {"description": description})
                first = next(l[2:] for l in text.split("\n") if l.startswith("* "))
                self.assertEqual(first, expected)

    def test_result_carries_a_runnable_check(self) -> None:
        self.handshake()
        text = self.client.call_text("from_symptom", {"description": "the page is blank"})
        self.assertIn("CHECK:", text)
        self.assertIn("NS-", text)

    def test_no_match_lists_the_available_symptoms(self) -> None:
        self.handshake()
        text = self.client.call_text(
            "from_symptom", {"description": "zzzqqq unrelated gibberish"})
        self.assertIn("Nothing matched", text)
        for sy in self.registry["symptoms"]:
            self.assertIn(sy["symptom"], text)

    def test_empty_description_is_a_tool_error(self) -> None:
        self.handshake()
        result = self.client.call_tool("from_symptom", {"description": "   "})["result"]
        self.assertTrue(result.get("isError"))

    def test_missing_argument_is_a_tool_error(self) -> None:
        self.handshake()
        result = self.client.call_tool("from_symptom", {})["result"]
        self.assertTrue(result.get("isError"))

    def test_every_symptom_points_at_real_entries(self) -> None:
        self.handshake()
        ids = {e["id"] for e in self.registry["entries"]}
        for sy in self.registry["symptoms"]:
            with self.subTest(symptom=sy["symptom"]):
                self.assertTrue(sy["entries"])
                for eid in sy["entries"]:
                    self.assertIn(eid, ids)


class TestBeforeClaiming(MCPTestCase):
    """The task-first door. Asserts on how someone would describe what they
    just did, not on the wording of the recipe."""

    def test_plain_tasks_reach_the_right_recipe(self) -> None:
        self.handshake()
        cases = [
            ("I copied the built files to the web root", "I deployed a static site"),
            ("restarted the systemd unit", "I restarted a service"),
            ("edited the nginx config", "I changed a configuration file"),
            ("the test suite is green", "I ran the test suite and it passed"),
            ("took a screenshot of the page", "I checked that a page renders correctly"),
            ("uploaded the package to pypi", "I published a package or release"),
            ("downloaded a json file from an api", "I fetched or scraped a resource"),
            ("the container got OOM killed",
             "The machine is slow, or something ran out of memory"),
        ]
        for task, expected in cases:
            with self.subTest(task=task):
                text = self.client.call_text("before_claiming", {"task": task})
                first = next(l[3:-3] for l in text.split("\n") if l.startswith("== "))
                self.assertEqual(first, expected)

    def test_steps_carry_a_command_and_what_they_guard(self) -> None:
        self.handshake()
        text = self.client.call_text("before_claiming", {"task": "restarted the service"})
        self.assertIn("$ ", text)
        self.assertIn("guards against:", text)
        self.assertIn("NS-", text)

    def test_nonsense_lists_the_covered_tasks(self) -> None:
        self.handshake()
        text = self.client.call_text("before_claiming", {"task": "zzz nonsense words here"})
        self.assertIn("No preflight matches", text)
        for r in self.registry["recipes"]:
            self.assertIn(r["task"], text)

    def test_empty_task_is_a_tool_error(self) -> None:
        self.handshake()
        self.assertTrue(self.client.call_tool("before_claiming", {"task": " "})["result"]
                        .get("isError"))

    def test_every_recipe_step_guards_a_real_entry(self) -> None:
        self.handshake()
        ids = {e["id"] for e in self.registry["entries"]}
        for r in self.registry["recipes"]:
            for st in r["steps"]:
                with self.subTest(recipe=r["id"], check=st["check"][:40]):
                    self.assertTrue(st["guards_against"])
                    for g in st["guards_against"]:
                        self.assertIn(g, ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
