"""Basescan activity backend for Base wallet tracking.

The Basescan API uses the Etherscan v2-compatible account endpoints with
``chainid=8453`` for Base mainnet.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Callable, Optional

from scout.activity import ActivityBackend, WalletActivity, identify_protocol

logger = logging.getLogger(__name__)

BASE_CHAIN_ID = 8453
BASESCAN_API_BASE = "https://api.etherscan.io/v2/api"
NO_TRANSACTIONS = "no transactions"


class BasescanBackend(ActivityBackend):
    """Base-specific backend using the Etherscan v2-compatible Basescan API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASESCAN_API_BASE,
        session_factory: Optional[Callable[[], Any]] = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("BASESCAN_API_KEY")
            or os.environ.get("ETHERSCAN_API_KEY", "")
        )
        self.base_url = base_url
        self._session_factory = session_factory
        if not self.api_key:
            logger.warning(
                "BASESCAN_API_KEY or ETHERSCAN_API_KEY not set; Basescan v2 requires a key."
            )

    async def fetch(self, address: str, chain: str = "base", limit: int = 20) -> list[WalletActivity]:
        """Fetch recent Base transactions and token transfers for a wallet."""
        if chain.lower() != "base":
            logger.warning("BasescanBackend only supports base; got %s", chain)
            return []

        history = await self.fetch_transaction_history(address, limit=limit)
        token_transfers = await self.fetch_token_transfers(address, limit=limit)
        return self._sort_and_limit(history + token_transfers, limit)

    async def fetch_transaction_history(self, address: str, limit: int = 20) -> list[WalletActivity]:
        """Fetch normal transaction history for an address on Base."""
        rows = await self._fetch_account_rows("txlist", address, limit)
        return [self._activity_from_transaction(address, row) for row in rows]

    async def fetch_token_transfers(self, address: str, limit: int = 20) -> list[WalletActivity]:
        """Fetch ERC-20 token transfers for an address on Base."""
        rows = await self._fetch_account_rows("tokentx", address, limit)
        return [self._activity_from_token_transfer(address, row) for row in rows]

    async def fetch_contract_interactions(self, address: str, limit: int = 20) -> list[WalletActivity]:
        """Fetch normal transactions that include contract call input data."""
        rows = await self._fetch_account_rows("txlist", address, limit)
        contract_rows = [
            row for row in rows if row.get("to") and str(row.get("input", "")).lower() not in ("", "0x")
        ]
        return [self._activity_from_transaction(address, row) for row in contract_rows]

    async def _fetch_account_rows(
        self,
        action: str,
        address: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError(
                "aiohttp not installed. Install with: pip install scout-onchain[activity]"
            )

        params = {
            "chainid": BASE_CHAIN_ID,
            "module": "account",
            "action": action,
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.api_key,
        }

        session_factory = self._session_factory or aiohttp.ClientSession
        try:
            async with session_factory() as session:
                async with session.get(
                    self.base_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("basescan returned %d for %s/%s", resp.status, address, action)
                        return []
                    data = await resp.json()
        except Exception as exc:
            logger.warning("basescan fetch failed for %s/%s: %s", address, action, exc)
            return []

        if str(data.get("status")) != "1":
            message = str(data.get("message", ""))
            if message and NO_TRANSACTIONS not in message.lower():
                logger.warning("basescan error for %s/%s: %s", address, action, message)
            return []

        result = data.get("result", [])
        return result if isinstance(result, list) else []

    @staticmethod
    def _activity_from_transaction(address: str, tx: dict[str, Any]) -> WalletActivity:
        to_address = str(tx.get("to", "") or "")
        return WalletActivity(
            address=address,
            chain="base",
            protocol=identify_protocol(to_address),
            to_address=to_address,
            timestamp=_timestamp(tx),
            tx_hash=str(tx.get("hash", "") or ""),
            value_eth=_wei_to_eth(tx.get("value", 0)),
        )

    @staticmethod
    def _activity_from_token_transfer(address: str, tx: dict[str, Any]) -> WalletActivity:
        contract = str(tx.get("contractAddress", "") or "")
        protocol = identify_protocol(contract)
        if protocol == "unknown":
            protocol = str(tx.get("tokenSymbol", "") or tx.get("tokenName", "") or "unknown")
        return WalletActivity(
            address=address,
            chain="base",
            protocol=protocol,
            to_address=contract,
            timestamp=_timestamp(tx),
            tx_hash=str(tx.get("hash", "") or ""),
            value_eth=0.0,
        )

    @staticmethod
    def _sort_and_limit(activities: list[WalletActivity], limit: int) -> list[WalletActivity]:
        return sorted(activities, key=lambda activity: activity.timestamp, reverse=True)[:limit]


def _timestamp(row: dict[str, Any]) -> datetime:
    try:
        return datetime.fromtimestamp(int(row.get("timeStamp", 0)))
    except (TypeError, ValueError):
        return datetime.fromtimestamp(0)


def _wei_to_eth(value: Any) -> float:
    try:
        return float(value) / 1e18
    except (TypeError, ValueError):
        return 0.0
