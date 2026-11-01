"""Frozen HTTP contract and shared runtime checks for the router split."""
import asyncio
import json
import unittest
from pathlib import Path

from swarmbalance.web.app import app
from swarmbalance.web.dependencies import runtime
from swarmbalance.web.routes import simulation, tasks, checkpoints


async def _request(path, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
               "scheme": "http", "method": method, "path": path, "raw_path": path.encode(),
               "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")],
               "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8765)}, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(body)


class HTTPContractTests(unittest.TestCase):
    def test_full_openapi_matches_pre_refactor_contract(self):
        path = Path(__file__).with_name("fixtures") / "http_contract.json"
        self.assertEqual(app.openapi(), json.loads(path.read_text(encoding="utf-8")))

    def test_domain_routers_share_the_same_runtime(self):
        self.assertIs(simulation.runtime, runtime)
        self.assertIs(tasks.runtime, runtime)
        self.assertIs(checkpoints.runtime, runtime)

    def test_invalid_algorithm_and_seed_keep_http_400(self):
        for payload in ({"algorithm": "unknown", "seed": 100}, {"algorithm": "ga", "seed": -1}):
            status, response = asyncio.run(_request("/api/reset", "POST", payload))
            self.assertEqual(status, 400)
            self.assertTrue(response["detail"])

    def test_config_and_empty_comparison_keep_existing_shapes(self):
        status, config = asyncio.run(_request("/api/config"))
        self.assertEqual(status, 200)
        self.assertIn("environment", config)
        status, comparison = asyncio.run(_request("/api/compare"))
        self.assertEqual(status, 200)
        self.assertIn("rows", comparison)


if __name__ == "__main__":
    unittest.main()
