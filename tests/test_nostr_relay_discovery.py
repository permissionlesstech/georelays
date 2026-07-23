import asyncio
import hashlib
import json
import unittest
from unittest.mock import patch

from coincurve import PublicKeyXOnly

from nostr_relay_discovery import NostrRelayDiscovery


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def recv(self):
        return next(self.messages)

    async def send(self, message):
        self.sent.append(json.loads(message))


class Nip42Tests(unittest.TestCase):
    def setUp(self):
        self.discovery = NostrRelayDiscovery(
            "wss://relay.example.com",
            private_key="01".zfill(64),
        )

    def test_build_auth_event_is_valid_schnorr_event(self):
        with patch("nostr_relay_discovery.time.time", return_value=1_700_000_000):
            event = self.discovery.build_auth_event(
                "wss://relay.example.com", "challenge"
            )

        serialized = json.dumps(
            [
                0,
                event["pubkey"],
                event["created_at"],
                event["kind"],
                event["tags"],
                event["content"],
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        event_id = hashlib.sha256(serialized).digest()

        self.assertEqual(event["id"], event_id.hex())
        self.assertTrue(
            PublicKeyXOnly(bytes.fromhex(event["pubkey"])).verify(
                bytes.fromhex(event["sig"]), event_id
            )
        )

    def test_receive_with_auth_returns_subscription_response(self):
        async def run_test():
            auth_event = self.discovery.build_auth_event(
                "wss://relay.example.com", "challenge"
            )
            websocket = FakeWebSocket(
                [
                    json.dumps(["AUTH", "challenge"]),
                    json.dumps(
                        ["CLOSED", "subscription", "auth-required: authenticate"]
                    ),
                    json.dumps(["OK", auth_event["id"], True, ""]),
                    json.dumps(["EOSE", "subscription"]),
                ]
            )

            with patch.object(
                self.discovery, "build_auth_event", return_value=auth_event
            ):
                response = await self.discovery.receive_with_auth(
                    websocket,
                    "wss://relay.example.com",
                    5,
                    ["REQ", "subscription", {"kinds": [1]}],
                )

            self.assertEqual(response, ["EOSE", "subscription"])
            self.assertEqual(
                websocket.sent,
                [
                    ["AUTH", auth_event],
                    ["REQ", "subscription", {"kinds": [1]}],
                ],
            )

        asyncio.run(run_test())

    def test_receive_with_auth_reports_rejection(self):
        async def run_test():
            auth_event = self.discovery.build_auth_event(
                "wss://relay.example.com", "challenge"
            )
            websocket = FakeWebSocket(
                [
                    json.dumps(["AUTH", "challenge"]),
                    json.dumps(
                        ["OK", auth_event["id"], False, "restricted: not a member"]
                    ),
                ]
            )

            with patch.object(
                self.discovery, "build_auth_event", return_value=auth_event
            ):
                with self.assertRaisesRegex(PermissionError, "not a member"):
                    await self.discovery.receive_with_auth(
                        websocket, "wss://relay.example.com", 5
                    )

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
