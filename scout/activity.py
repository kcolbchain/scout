"""WalletTracker — follow wallets across chains, aggregate protocol signals.

Use cases:
- Smart-money following: which protocols are early airdrop hunters touching?
- Treasury monitoring: which DEXes does this whale prefer?
- Governance intel: where is this delegate active?
- Compliance: which contracts has this address ever touched?

Default backend is Etherscan v2 (multichain) with API key. Other backends
(Alchemy, Covalent, your own indexer) can be plugged in by subclassing
ActivityBackend.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


# Etherscan v2 unified multichain API (Aug 2024+)
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"

CHAIN_IDS = {
    "ethereum": 1,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "polygon": 137,
    "bsc": 56,
    "scroll": 534352,
    "linea": 59144,
}


@dataclass
class WalletActivity:
    address: str
    chain: str
    protocol: str  # resolved name or 'unknown'
    to_address: str
    timestamp: datetime
    tx_hash: str
    value_eth: float = 0.0


@dataclass
class TrackedWallet:
    """A wallet we're following. Can be `WalletLike` for FitScorer too."""

    address: str
    label: str
    tags: list[str] = field(default_factory=list)
    recent_activity: list[WalletActivity] = field(default_factory=list)

    # WalletLike protocol implementation
    @property
    def total_gas_spent(self) -> float:
        return 0.0  # tracker doesn't compute gas; subclass to add

    @property
    def unique_days_active(self) -> int:
        return len({a.timestamp.date() for a in self.recent_activity})

    @property
    def unique_protocols(self) -> set[str]:
        return {a.protocol for a in self.recent_activity if a.protocol != "unknown"}

    @property
    def activity(self):  # WalletLike interface
        # Adapt WalletActivity → object with .action and .chain
        return [_ActivityAdapter(a) for a in self.recent_activity]


@dataclass
class _ActivityAdapter:
    """Adapt a WalletActivity to look like monsoon's wallet_manager.WalletActivity."""

    inner: WalletActivity

    @property
    def chain(self) -> str:
        return self.inner.chain

    @property
    def action(self) -> str:
        return f"tx to {self.inner.protocol}"


# ---------- protocol resolution ----------

def _load_known_contracts() -> dict[str, str]:
    """Load address → protocol-name map from bundled data."""
    try:
        text = resources.files("scout").joinpath("data/known_contracts.yaml").read_text()
        data = yaml.safe_load(text) or {}
        return {addr.lower(): name for addr, name in data.get("contracts", {}).items()}
    except FileNotFoundError:
        return {}


_KNOWN_CONTRACTS = _load_known_contracts()


def identify_protocol(to_address: str) -> str:
    return _KNOWN_CONTRACTS.get((to_address or "").lower(), "unknown")


# ---------- backend abstraction ----------

class ActivityBackend:
    """Abstract backend for fetching wallet activity. Subclass to use Alchemy/Covalent/etc."""

    async def fetch(self, address: str, chain: str, limit: int = 20) -> list[WalletActivity]:
        raise NotImplementedError


class EtherscanBackend(ActivityBackend):
    """Etherscan v2 unified multichain API. Requires ETHERSCAN_API_KEY."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ETHERSCAN_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "ETHERSCAN_API_KEY not set; Etherscan v2 requires a key. "
                "Get one free at https://etherscan.io/apis"
            )

    async def fetch(self, address: str, chain: str, limit: int = 20) -> list[WalletActivity]:
        chain_id = CHAIN_IDS.get(chain)
        if chain_id is None:
            logger.warning("unknown chain %s; skipping", chain)
            return []

        # Lazy import so scout works without aiohttp installed if you only use Registry/FitScorer.
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError(
                "aiohttp not installed. Install with: pip install scout-onchain[activity]"
            )

        params = {
            "chainid": chain_id,
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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    ETHERSCAN_V2_BASE,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("etherscan v2 returned %d for %s/%s", resp.status, address, chain)
                        return []
                    data = await resp.json()
                    if str(data.get("status")) != "1":
                        msg = data.get("message", "")
                        if msg and "no transactions" not in msg.lower():
                            logger.warning("etherscan v2 error for %s/%s: %s", address, chain, msg)
                        return []
                    return [
                        WalletActivity(
                            address=address,
                            chain=chain,
                            protocol=identify_protocol(tx.get("to", "")),
                            to_address=tx.get("to", ""),
                            timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                            tx_hash=tx.get("hash", ""),
                            value_eth=float(tx.get("value", 0)) / 1e18,
                        )
                        for tx in data.get("result", [])
                    ]
        except Exception as exc:
            logger.warning("etherscan fetch failed for %s/%s: %s", address, chain, exc)
            return []


# ---------- WalletTracker ----------

class WalletTracker:
    """Tracks a set of wallets across chains and aggregates protocol signals."""

    DEFAULT_CHAINS = ["ethereum", "arbitrum", "optimism", "base"]

    def __init__(
        self,
        wallets: Optional[list[TrackedWallet]] = None,
        backend: Optional[ActivityBackend] = None,
    ):
        self.wallets: list[TrackedWallet] = list(wallets or [])
        self.backend: ActivityBackend = backend or EtherscanBackend()

    @classmethod
    def load_alpha(cls, path: Optional[Path] = None) -> "WalletTracker":
        """Load the bundled curated alpha-wallet list."""
        if path is None:
            text = resources.files("scout").joinpath("data/alpha_wallets.yaml").read_text()
        else:
            text = Path(path).read_text()
        data = yaml.safe_load(text) or {}
        wallets = [
            TrackedWallet(
                address=w["address"],
                label=w.get("label", w["address"][:10]),
                tags=w.get("tags", []) or [],
            )
            for w in data.get("wallets", [])
        ]
        return cls(wallets=wallets)

    async def refresh(self, chains: Optional[list[str]] = None, limit: int = 20) -> None:
        """Re-fetch recent activity for all tracked wallets across the given chains."""
        chains = chains or self.DEFAULT_CHAINS
        for wallet in self.wallets:
            all_activity: list[WalletActivity] = []
            for chain in chains:
                acts = await self.backend.fetch(wallet.address, chain, limit=limit)
                all_activity.extend(acts)
            wallet.recent_activity = all_activity
            logger.info("refreshed %s: %d txns across %d chains",
                        wallet.label, len(all_activity), len(chains))

    def refresh_sync(self, chains: Optional[list[str]] = None, limit: int = 20) -> None:
        """Synchronous wrapper around refresh()."""
        asyncio.run(self.refresh(chains=chains, limit=limit))

    def protocol_signals(self) -> dict[str, int]:
        """Aggregate: which protocols are tracked wallets touching most?"""
        counts: dict[str, int] = {}
        for w in self.wallets:
            for a in w.recent_activity:
                if a.protocol != "unknown":
                    counts[a.protocol] = counts.get(a.protocol, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def chain_signals(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for w in self.wallets:
            for a in w.recent_activity:
                counts[a.chain] = counts.get(a.chain, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
