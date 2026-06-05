from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from scout.activity import ActivityBackend, WalletActivity, identify_protocol

logger = logging.getLogger(__name__)

BASESCAN_API_BASE = "https://api.basescan.org/api"

class BasescanBackend(ActivityBackend):
    """Basescan API backend for Base chain activity. Compatible with Etherscan v2 format."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BASESCAN_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "BASESCAN_API_KEY not set. Basescan requests will be severely rate-limited."
            )

    async def fetch(self, address: str, chain: str, limit: int = 20) -> list[WalletActivity]:
        if chain.lower() != "base":
            logger.warning("BasescanBackend only supports the 'base' chain; got %s", chain)
            return []

        try:
            import aiohttp
        except ImportError:
            raise RuntimeError(
                "aiohttp not installed. Install with: pip install scout-onchain[activity]"
            )

        activities = []
        async with aiohttp.ClientSession() as session:
            # 1. Fetch normal transactions (transaction history, contract interactions)
            txlist_params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": limit,
                "sort": "desc",
            }
            if self.api_key:
                txlist_params["apikey"] = self.api_key

            try:
                async with session.get(
                    BASESCAN_API_BASE,
                    params=txlist_params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if str(data.get("status")) == "1":
                            for tx in data.get("result", []):
                                activities.append(
                                    WalletActivity(
                                        address=address,
                                        chain=chain,
                                        protocol=identify_protocol(tx.get("to", "")),
                                        to_address=tx.get("to", ""),
                                        timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                                        tx_hash=tx.get("hash", ""),
                                        value_eth=float(tx.get("value", 0)) / 1e18,
                                    )
                                )
            except Exception as exc:
                logger.warning("basescan txlist fetch failed for %s: %s", address, exc)

            # 2. Fetch ERC20 token transfers
            tokentx_params = {
                "module": "account",
                "action": "tokentx",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": limit,
                "sort": "desc",
            }
            if self.api_key:
                tokentx_params["apikey"] = self.api_key

            try:
                async with session.get(
                    BASESCAN_API_BASE,
                    params=tokentx_params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if str(data.get("status")) == "1":
                            for tx in data.get("result", []):
                                activities.append(
                                    WalletActivity(
                                        address=address,
                                        chain=chain,
                                        protocol=identify_protocol(tx.get("contractAddress", "")),
                                        to_address=tx.get("to", ""),
                                        timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                                        tx_hash=tx.get("hash", ""),
                                        value_eth=0.0, # token transfers do not transfer ETH
                                    )
                                )
            except Exception as exc:
                logger.warning("basescan tokentx fetch failed for %s: %s", address, exc)

        # Sort combined activities by timestamp desc and apply limit
        activities.sort(key=lambda a: a.timestamp, reverse=True)
        # Deduplicate by tx_hash if needed, though txlist and tokentx can share hashes.
        # Returning up to `limit` as requested.
        return activities[:limit]
