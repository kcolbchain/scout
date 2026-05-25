"""scout — on-chain wallet & protocol intelligence primitives.

Three composable parts:

- Registry: a curated, queryable database of protocols (Targets) with
  category, confidence, criteria, contracts, and notes.
- FitScorer: scores any wallet against any target's criteria.
- WalletTracker: follows wallets across chains, aggregates protocol signals.

Used by airdrop farming agents, due-diligence research, treasury monitoring,
wallet reputation scoring, governance intelligence, and ecosystem mapping.
"""

from .registry import Registry, Target, Confidence
from .scoring import FitScorer, FitScore
from .activity import WalletTracker, WalletActivity, TrackedWallet
from .cluster import build_clusters, cluster_penalty

__version__ = "0.1.0"
__all__ = [
    "Registry",
    "Target",
    "Confidence",
    "FitScorer",
    "FitScore",
    "WalletTracker",
    "WalletActivity",
    "TrackedWallet",
    "build_clusters",
    "cluster_penalty",
]
