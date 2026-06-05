"""Tests for the Base activity backend."""

import asyncio

from scout.backends import BasescanBackend


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads, calls):
        self.payloads = payloads
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        return FakeResponse(self.payloads[params["action"]])


def make_backend(payloads):
    calls = []
    backend = BasescanBackend(
        api_key="test-key",
        session_factory=lambda: FakeSession(payloads, calls),
    )
    return backend, calls


def test_fetch_combines_base_transaction_history_and_token_transfers():
    payloads = {
        "txlist": {
            "status": "1",
            "result": [
                {
                    "to": "0x111",
                    "timeStamp": "1780000000",
                    "hash": "0xnormal",
                    "value": "1000000000000000000",
                    "input": "0x",
                }
            ],
        },
        "tokentx": {
            "status": "1",
            "result": [
                {
                    "contractAddress": "0x222",
                    "tokenSymbol": "USDC",
                    "timeStamp": "1780000100",
                    "hash": "0xtoken",
                }
            ],
        },
    }
    backend, calls = make_backend(payloads)

    activities = asyncio.run(backend.fetch("0xwallet", "base", limit=10))

    assert [params["action"] for _, params in calls] == ["txlist", "tokentx"]
    assert all(params["chainid"] == 8453 for _, params in calls)
    assert [activity.tx_hash for activity in activities] == ["0xtoken", "0xnormal"]
    assert activities[0].protocol == "USDC"
    assert activities[1].value_eth == 1.0


def test_fetch_contract_interactions_filters_normal_transactions_with_input():
    payloads = {
        "txlist": {
            "status": "1",
            "result": [
                {
                    "to": "0xcontract",
                    "timeStamp": "1780000200",
                    "hash": "0xcall",
                    "value": "0",
                    "input": "0xabcdef",
                },
                {
                    "to": "0xeoa",
                    "timeStamp": "1780000000",
                    "hash": "0xtransfer",
                    "value": "1000",
                    "input": "0x",
                },
            ],
        }
    }
    backend, calls = make_backend(payloads)

    interactions = asyncio.run(backend.fetch_contract_interactions("0xwallet", limit=10))

    assert [params["action"] for _, params in calls] == ["txlist"]
    assert [activity.tx_hash for activity in interactions] == ["0xcall"]
    assert interactions[0].to_address == "0xcontract"


def test_non_base_chain_is_ignored():
    backend, calls = make_backend({})

    activities = asyncio.run(backend.fetch("0xwallet", "ethereum", limit=10))

    assert activities == []
    assert calls == []
