"""Tests for scout.backends.basescan — mocked API responses."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scout.backends.basescan import BASESCAN_API_BASE, BasescanBackend
from scout.activity import WalletActivity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def backend():
    return BasescanBackend(api_key="test-key-123")


@pytest.fixture
def mock_normal_tx_response():
    """Sample Basescan normal transaction response."""
    return {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "hash": "0xabc123",
                "to": "0xdef456",
                "from": "0x111222333",
                "value": "1000000000000000000",  # 1 ETH
                "timeStamp": "1700000000",
                "blockNumber": "12345",
            },
            {
                "hash": "0xabc456",
                "to": "0x789abc",
                "from": "0x111222333",
                "value": "500000000000000000",  # 0.5 ETH
                "timeStamp": "1700000100",
                "blockNumber": "12346",
            },
        ],
    }


@pytest.fixture
def mock_token_tx_response():
    """Sample Basescan ERC-20 token transfer response."""
    return {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "hash": "0xtoken1",
                "to": "0xrecipient",
                "from": "0x111222333",
                "value": "2000000",
                "timeStamp": "1700000200",
                "contractAddress": "0xusdc_contract",
                "tokenSymbol": "USDC",
            },
        ],
    }


@pytest.fixture
def mock_internal_tx_response():
    """Sample Basescan internal transaction response."""
    return {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "hash": "0xinternal1",
                "to": "0xrouter_contract",
                "from": "0x111222333",
                "value": "300000000000000000",
                "timeStamp": "1700000300",
            },
        ],
    }


@pytest.fixture
def mock_empty_response():
    """Basescan empty / no transactions response."""
    return {
        "status": "0",
        "message": "No transactions found",
        "result": [],
    }


# ---------------------------------------------------------------------------
# Tests: init
# ---------------------------------------------------------------------------

def test_backend_init_with_key():
    b = BasescanBackend(api_key="mykey")
    assert b.api_key == "mykey"


def test_backend_init_from_env():
    with patch.dict("os.environ", {"BASESCAN_API_KEY": "envkey"}):
        b = BasescanBackend()
        assert b.api_key == "envkey"


def test_backend_init_no_key_warns(caplog):
    with patch.dict("os.environ", {}, clear=True):
        import logging
        with caplog.at_level(logging.WARNING):
            b = BasescanBackend()
            assert "BASESCAN_API_KEY not set" in caplog.text


# ---------------------------------------------------------------------------
# Tests: fetch with mocked HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_normal_txs(backend, mock_normal_tx_response):
    """Normal transactions are parsed into WalletActivity objects."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=mock_normal_tx_response)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("scout.backends.basescan._require_aiohttp") as mock_aio:
        aiohttp_mod = MagicMock()
        aiohttp_mod.ClientSession = MagicMock(return_value=mock_session)
        aiohttp_mod.ClientTimeout = MagicMock(return_value=None)
        mock_aio.return_value = aiohttp_mod

        results = await backend.fetch("0x111222333", limit=10)

    # Should have normal + token + internal results from their respective responses
    # But since we mock the same session.get, all three calls use the same mock_resp
    # With dedup, we get unique hashes
    assert len(results) > 0
    assert all(isinstance(a, WalletActivity) for a in results)
    assert all(a.chain == "base" for a in results)


@pytest.mark.asyncio
async def test_fetch_empty_response(backend, mock_empty_response):
    """Empty API response returns empty list."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=mock_empty_response)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("scout.backends.basescan._require_aiohttp") as mock_aio:
        aiohttp_mod = MagicMock()
        aiohttp_mod.ClientSession = MagicMock(return_value=mock_session)
        aiohttp_mod.ClientTimeout = MagicMock(return_value=None)
        mock_aio.return_value = aiohttp_mod

        results = await backend.fetch("0xdeadbeef")
        assert results == []


@pytest.mark.asyncio
async def test_fetch_deduplication(backend):
    """Same tx_hash in normal and internal should be deduplicated."""
    response = {
        "status": "1",
        "message": "OK",
        "result": [
            {
                "hash": "0xdup1",
                "to": "0xaaa",
                "from": "0x111222333",
                "value": "1000000000000000000",
                "timeStamp": "1700000000",
            },
        ],
    }

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=response)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("scout.backends.basescan._require_aiohttp") as mock_aio:
        aiohttp_mod = MagicMock()
        aiohttp_mod.ClientSession = MagicMock(return_value=mock_session)
        aiohttp_mod.ClientTimeout = MagicMock(return_value=None)
        mock_aio.return_value = aiohttp_mod

        results = await backend.fetch("0x111222333", limit=10)

    # All three fetchers return same hash → deduplicated to 1
    seen_hashes = [a.tx_hash for a in results]
    assert len(seen_hashes) == len(set(seen_hashes))


# ---------------------------------------------------------------------------
# Tests: parse helpers
# ---------------------------------------------------------------------------

def test_parse_timestamp_valid():
    ts = BasescanBackend._parse_timestamp("1700000000")
    assert isinstance(ts, datetime)
    assert ts.year == 2023


def test_parse_timestamp_invalid():
    ts = BasescanBackend._parse_timestamp("not-a-number")
    assert ts == datetime.min


def test_parse_timestamp_empty():
    ts = BasescanBackend._parse_timestamp("0")
    assert isinstance(ts, datetime)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

def test_parse_txs_with_non_dict_result(backend):
    """API sometimes returns a string error message instead of a list."""
    data = {"status": "0", "result": "Max rate limit reached"}
    results = backend._parse_txs(data, "0xaddr")
    assert results == []


def test_parse_token_txs_with_missing_fields(backend):
    """Token tx with missing contractAddress should use to_address."""
    data = {
        "status": "1",
        "result": [
            {
                "hash": "0xtk1",
                "to": "0xbbb",
                "value": "100",
                "timeStamp": "1700000000",
            },
        ],
    }
    results = backend._parse_token_txs(data, "0xaddr")
    assert len(results) == 1
    assert results[0].to_address == "0xbbb"


def test_parse_internal_txs_empty(backend):
    data = {"status": "0", "result": []}
    results = backend._parse_internal_txs(data, "0xaddr")
    assert results == []


@pytest.mark.asyncio
async def test_fetch_http_error(backend):
    """Non-200 HTTP status should return empty results."""
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("scout.backends.basescan._require_aiohttp") as mock_aio:
        aiohttp_mod = MagicMock()
        aiohttp_mod.ClientSession = MagicMock(return_value=mock_session)
        aiohttp_mod.ClientTimeout = MagicMock(return_value=None)
        mock_aio.return_value = aiohttp_mod

        results = await backend.fetch("0x111222333")
        assert results == []
