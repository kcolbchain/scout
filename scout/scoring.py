"""FitScorer — score how well a wallet matches a target's criteria.

The same primitive serves multiple use cases:

- Airdrop eligibility ("does this wallet meet the criteria for the LayerZero airdrop?")
- Allowlist gating ("does this wallet meet the requirements for our perp DEX onboarding?")
- Lending risk ("does this wallet have enough on-chain history to qualify for an under-collateralized loan?")
- KYC-lite reputation ("does this wallet behave like a real user, not a sybil?")

Inputs are intentionally minimal: a wallet snapshot (activity history) and a
target with a `criteria` dict. The scorer is data-driven, not airdrop-specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .registry import Target


class WalletLike(Protocol):
    """Minimal interface a wallet snapshot must satisfy to be scored.

    Implementations: monsoon's WalletManager.Wallet, scout's WalletTracker.TrackedWallet,
    or any custom user object that exposes these attributes.
    """

    address: str

    @property
    def total_gas_spent(self) -> float: ...
    @property
    def unique_days_active(self) -> int: ...
    @property
    def unique_protocols(self) -> set[str]: ...

    activity: list  # iterable of objects with `.action` and `.chain`


@dataclass
class FitScore:
    target: str
    wallet: str
    score: float  # 0-100
    met: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        if self.score >= 80:
            return "A"
        if self.score >= 60:
            return "B"
        if self.score >= 40:
            return "C"
        if self.score >= 20:
            return "D"
        return "F"


class FitScorer:
    """Score a wallet against any Target's criteria dict.

    Criteria keys recognized:
      bridge_volume / bridge_usage / cross_chain_messages → bridge activity (15 pts)
      dex_swaps / dex_interaction / swap_volume          → DEX activity (15 pts)
      unique_months                                       → multi-month consistency (20 pts)
      restake_eth / bgt_staking / sats_campaign / lp_provision → manual flags (recommendation only)
      testnet_activity                                    → manual flag (recommendation only)

    Plus universal heuristics that always apply:
      protocol diversity (≥3 distinct protocols)         → 10 pts
      chain diversity   (≥3 distinct chains)             → 10 pts
      gas spend         (≥0.05 native units)             → 10 pts
      long-term user    (≥30 unique active days)         → 10 pts
    """

    def score(self, wallet: WalletLike, target: Target) -> FitScore:
        met: list[str] = []
        missing: list[str] = []
        recs: list[str] = []
        s = 0.0
        criteria = target.criteria or {}

        # Bridge activity
        if any(k in criteria for k in ("bridge_volume", "bridge_usage", "cross_chain_messages")):
            n = sum(1 for a in wallet.activity if "bridge" in a.action.lower())
            if n >= 3:
                met.append(f"Bridge activity ({n} txns)")
                s += 15
            else:
                missing.append(f"Bridge activity (have {n}, need 3+)")
                recs.append(f"Bridge to {target.chain} via Stargate or Across")

        # DEX activity
        if any(k in criteria for k in ("dex_swaps", "dex_interaction", "swap_volume")):
            n = sum(1 for a in wallet.activity if "swap" in a.action.lower())
            if n >= 5:
                met.append(f"DEX swaps ({n} txns)")
                s += 15
            else:
                missing.append(f"DEX swaps (have {n}, need 5+)")
                recs.append(f"Swap on native DEXes on {target.chain}")

        # Multi-month consistency
        if "unique_months" in criteria:
            target_months = self._extract_int(criteria["unique_months"], default=3)
            days = wallet.unique_days_active
            if days >= target_months * 4:  # ~4 active days per month
                met.append(f"Active {days} days across {target_months}+ months")
                s += 20
            else:
                missing.append(f"Activity consistency (need {target_months}+ months)")
                recs.append("Maintain regular activity over multiple months")

        # Universal heuristics
        if len(wallet.unique_protocols) >= 3:
            met.append(f"Protocol diversity ({len(wallet.unique_protocols)})")
            s += 10
        else:
            missing.append(f"Protocol diversity (have {len(wallet.unique_protocols)}, want 3+)")
            recs.append("Interact with more protocols")

        unique_chains = len({a.chain for a in wallet.activity})
        if unique_chains >= 3:
            met.append(f"Chain diversity ({unique_chains})")
            s += 10
        else:
            missing.append(f"Chain diversity (have {unique_chains}, want 3+)")
            recs.append("Use bridges to interact with more chains")

        if wallet.total_gas_spent >= 0.05:
            met.append(f"Gas spent ({wallet.total_gas_spent:.3f})")
            s += 10
        else:
            missing.append("Gas spend low — looks new/inactive")
            recs.append("Increase organic transaction volume")

        if wallet.unique_days_active >= 30:
            met.append("Long-term user (30+ active days)")
            s += 10

        # Manual-check flags (no points, but recommendations)
        if criteria.get("testnet_activity"):
            missing.append("Testnet activity (verify manually)")
            recs.append(f"Participate in {target.name} testnet if available")
        if criteria.get("restake_eth") or criteria.get("bgt_staking") or criteria.get("sena_stake"):
            missing.append(f"Staking on {target.name} (verify manually)")
            recs.append(f"Stake / restake on {target.name}")
        if criteria.get("lp_provision"):
            recs.append(f"Provide liquidity on {target.name}")

        return FitScore(
            target=target.name,
            wallet=wallet.address,
            score=min(s, 100.0),
            met=met,
            missing=missing,
            recommendations=recs,
        )

    def score_all(self, wallet: WalletLike, targets: list[Target]) -> list[FitScore]:
        scores = [self.score(wallet, t) for t in targets]
        scores.sort(key=lambda x: x.score, reverse=True)
        return scores

    @staticmethod
    def _extract_int(value, default: int = 0) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(c for c in value if c.isdigit())
            return int(digits) if digits else default
        return default
