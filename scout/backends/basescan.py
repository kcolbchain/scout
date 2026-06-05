import logging
import os
from datetime import datetime
from typing import Optional

from scout.activity import ActivityBackend, WalletActivity, identify_protocol

logger = logging.getLogger(__name__)

BASESCAN_API_URL = "https://api.basescan.org/api"

class BasescanBackend(ActivityBackend):
    """Basescan API backend for Base chain activity tracking."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BASESCAN_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "BASESCAN_API_KEY not set. "
                "Get one free at https://basescan.org/apis"
            )

    async def fetch(self, address: str, chain: str, limit: int = 20) -> list[WalletActivity]:
        if chain != "base":
            logger.warning("BasescanBackend only supports 'base' chain")
            return []

        try:
            import aiohttp
        except ImportError:
            raise RuntimeError(
                "aiohttp not installed. Install with: pip install scout-onchain[activity]"
            )

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

        all_txs = []
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Normal transactions (history & interactions)
                tx_params = {**params, "action": "txlist"}
                async with session.get(BASESCAN_API_URL, params=tx_params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if str(data.get("status")) == "1":
                            for tx in data.get("result", []):
                                all_txs.append(WalletActivity(
                                    address=address,
                                    chain=chain,
                                    protocol=identify_protocol(tx.get("to", "")),
                                    to_address=tx.get("to", ""),
                                    timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                                    tx_hash=tx.get("hash", ""),
                                    value_eth=float(tx.get("value", 0)) / 1e18,
                                ))
                
                # 2. ERC20 token transfers
                token_params = {**params, "action": "tokentx"}
                async with session.get(BASESCAN_API_URL, params=token_params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if str(data.get("status")) == "1":
                            for tx in data.get("result", []):
                                # Skip if we already have this tx_hash from normal txs
                                if any(a.tx_hash == tx.get("hash", "") for a in all_txs):
                                    continue
                                all_txs.append(WalletActivity(
                                    address=address,
                                    chain=chain,
                                    protocol=identify_protocol(tx.get("contractAddress", "")),
                                    to_address=tx.get("contractAddress", ""),
                                    timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                                    tx_hash=tx.get("hash", ""),
                                    value_eth=0.0, # Could map token value, but keeping simple
                                ))
                                
            # Sort by timestamp desc and apply limit
            all_txs.sort(key=lambda x: x.timestamp, reverse=True)
            return all_txs[:limit]
        except Exception as exc:
            logger.warning("basescan fetch failed for %s: %s", address, exc)
            return []
