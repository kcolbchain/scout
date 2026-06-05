"""Basescan API backend for Base chain activity tracking.

Implements the ActivityBackend interface from scout.activity, using the
Basescan API (https://api.basescan.org/api) which is fully compatible with
the Etherscan v2 API format.

Supports:
- Transaction history (normal txs)
- Token transfers (ERC-20 events)
- Contract interactions (internal txs)

Requires a BASESCAN_API_KEY environment variable (free at https://basescan.org/apis).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from scout.activity import ActivityBackend, WalletActivity, identify_protocol

if TYPE_CHECKING:
    import aiohttp as _aiohttp

logger = logging.getLogger(__name__)

BASESCAN_API_BASE = "https://api.basescan.org/api"
BASE_CHAIN_ID = 8453


def _require_aiohttp():
    """Lazy-import aiohttp, raising a clear error if missing."""
    try:
        import aiohttp
        return aiohttp
    except ImportError:
        raise RuntimeError(
            "aiohttp not installed. Install with: pip install scout-onchain[activity]"
        )


class BasescanBackend(ActivityBackend):
    """Basescan API backend for Base chain activity.

    Uses the Basescan REST API (Etherscan-compatible format) to fetch
    wallet transactions, token transfers, and internal transactions.

    Requires ``BASESCAN_API_KEY`` env var (free tier: 5 calls/sec).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BASESCAN_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "BASESCAN_API_KEY not set. Get a free key at https://basescan.org/apis"
            )

    async def fetch(self, address: str, chain: str = "base", limit: int = 20) -> list[WalletActivity]:
        """Fetch wallet activity from Basescan.

        Parameters
        ----------
        address : str
            Wallet address to query.
        chain : str
            Ignored (always 'base'). Accepted for interface compatibility.
        limit : int
            Max transactions per category.

        Returns
        -------
        list[WalletActivity]
            Combined activity from normal txs, token transfers, and internal txs.
        """
        aiohttp = _require_aiohttp()

        results: list[WalletActivity] = []

        async with aiohttp.ClientSession() as session:
            # 1. Normal transactions
            normal_txs = await self._fetch_normal_txs(session, address, limit)
            results.extend(normal_txs)

            # 2. Token transfers (ERC-20 events)
            token_txs = await self._fetch_token_transfers(session, address, limit)
            results.extend(token_txs)

            # 3. Internal transactions (contract interactions)
            internal_txs = await self._fetch_internal_txs(session, address, limit)
            results.extend(internal_txs)

        # Deduplicate by tx_hash (same hash can appear in normal + internal)
        seen: set[str] = set()
        unique: list[WalletActivity] = []
        for act in results:
            if act.tx_hash not in seen:
                seen.add(act.tx_hash)
                unique.append(act)

        # Sort by timestamp descending
        unique.sort(key=lambda a: a.timestamp, reverse=True)
        return unique[:limit]

    # ------------------------------------------------------------------
    # Internal fetchers
    # ------------------------------------------------------------------

    async def _fetch_normal_txs(
        self, session: Any, address: str, limit: int
    ) -> list[WalletActivity]:
        """Fetch normal (external) transactions."""
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.api_key,
        }
        data = await self._get(session, params)
        return self._parse_txs(data, address)

    async def _fetch_token_transfers(
        self, session: Any, address: str, limit: int
    ) -> list[WalletActivity]:
        """Fetch ERC-20 token transfer events."""
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.api_key,
        }
        data = await self._get(session, params)
        return self._parse_token_txs(data, address)

    async def _fetch_internal_txs(
        self, session: Any, address: str, limit: int
    ) -> list[WalletActivity]:
        """Fetch internal transactions (contract interactions)."""
        params = {
            "module": "account",
            "action": "txlistinternal",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.api_key,
        }
        data = await self._get(session, params)
        return self._parse_internal_txs(data, address)

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _get(
        self, session: Any, params: dict
    ) -> dict:
        """Execute a GET request against the Basescan API."""
        try:
            aiohttp = _require_aiohttp()
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(BASESCAN_API_BASE, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning("Basescan returned HTTP %d", resp.status)
                    return {"status": "0", "result": []}
                data = await resp.json()
                if str(data.get("status")) != "1":
                    msg = data.get("message", "")
                    if msg and "no transactions" not in msg.lower():
                        logger.warning("Basescan API error: %s", msg)
                return data
        except Exception as exc:
            logger.warning("Basescan fetch failed: %s", exc)
            return {"status": "0", "result": []}

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_txs(self, data: dict, address: str) -> list[WalletActivity]:
        """Parse normal transaction list response."""
        results = data.get("result", [])
        if not isinstance(results, list):
            return []
        activities = []
        for tx in results:
            if not isinstance(tx, dict):
                continue
            to_addr = tx.get("to", "")
            activities.append(
                WalletActivity(
                    address=address,
                    chain="base",
                    protocol=identify_protocol(to_addr),
                    to_address=to_addr,
                    timestamp=self._parse_timestamp(tx.get("timeStamp", "0")),
                    tx_hash=tx.get("hash", ""),
                    value_eth=float(tx.get("value", 0)) / 1e18,
                )
            )
        return activities

    def _parse_token_txs(self, data: dict, address: str) -> list[WalletActivity]:
        """Parse ERC-20 token transfer response."""
        results = data.get("result", [])
        if not isinstance(results, list):
            return []
        activities = []
        for tx in results:
            if not isinstance(tx, dict):
                continue
            to_addr = tx.get("to", "")
            # Token transfers include contractAddress (the token contract)
            token_contract = tx.get("contractAddress", "")
            activities.append(
                WalletActivity(
                    address=address,
                    chain="base",
                    protocol=identify_protocol(token_contract or to_addr),
                    to_address=to_addr,
                    timestamp=self._parse_timestamp(tx.get("timeStamp", "0")),
                    tx_hash=tx.get("hash", ""),
                    value_eth=float(tx.get("value", 0)) / 1e18,
                )
            )
        return activities

    def _parse_internal_txs(self, data: dict, address: str) -> list[WalletActivity]:
        """Parse internal transaction response."""
        results = data.get("result", [])
        if not isinstance(results, list):
            return []
        activities = []
        for tx in results:
            if not isinstance(tx, dict):
                continue
            to_addr = tx.get("to", "")
            # Internal txs use parent hash
            tx_hash = tx.get("hash", "")
            activities.append(
                WalletActivity(
                    address=address,
                    chain="base",
                    protocol=identify_protocol(to_addr),
                    to_address=to_addr,
                    timestamp=self._parse_timestamp(tx.get("timeStamp", "0")),
                    tx_hash=tx_hash,
                    value_eth=float(tx.get("value", 0)) / 1e18,
                )
            )
        return activities

    @staticmethod
    def _parse_timestamp(ts: str) -> datetime:
        """Parse unix timestamp string to datetime."""
        try:
            return datetime.fromtimestamp(int(ts))
        except (ValueError, OSError):
            return datetime.min
