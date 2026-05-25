"""Wallet clustering via funding-graph heuristics.

Groups addresses that share a common funder (sybil detection)
using a union-find data structure over two edge types:
- Shared-funder edge: two addresses funded by the same EOA within 48h
- Dust-fan-out edge: an EOA that sent small amounts to many addresses
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set, Tuple


class UnionFind:
    def __init__(self):
        self._parent: Dict[str, str] = {}
        self._rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            self._parent[ra] = rb
        elif self._rank[ra] > self._rank[rb]:
            self._parent[rb] = ra
        else:
            self._parent[rb] = ra
            self._rank[ra] += 1

    def groups(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = defaultdict(list)
        for key in self._parent:
            out[self.find(key)].append(key)
        return dict(out)


def build_clusters(funding_txs: List[dict]) -> Dict[str, List[str]]:
    """Build wallet clusters from a list of funding transactions.

    Each funding_tx dict:
      - from:  sender EOA address
      - to:    receiver address
      - value: amount in ETH equivalent (float)
      - block: block number (int)
      - timestamp: unix seconds (int)

    Returns {root_address: [member_address, ...]}.
    """
    uf = UnionFind()
    funder_to_receivers: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

    for tx in funding_txs:
        sender = tx["from"]
        receiver = tx["to"]
        value = float(tx.get("value", 0))
        ts = int(tx.get("timestamp", 0))

        # Dust-fan-out: sender sent < 5 ETH to many receivers
        if 0 < value < 5:
            funder_to_receivers[sender].append((receiver, ts))

        # Shared-funder: if >= 5 ETH, union sender with receiver
        if value >= 5:
            uf.union(sender, receiver)

    # Shared-funder edges via windowed grouping
    for sender, receivers in funder_to_receivers.items():
        if len(receivers) >= 10:
            # Dust-fan-out detected, union all receivers under the sender
            for r, _ in receivers:
                uf.union(sender, r)
        # Pairwise: union any two receivers funded within 48h by same EOA
        for i in range(len(receivers)):
            for j in range(i + 1, len(receivers)):
                ri, rj = receivers[i], receivers[j]
                if abs(ri[1] - rj[1]) <= 48 * 3600:
                    uf.union(ri[0], rj[0])

    return uf.groups()


def cluster_penalty(
    address: str, clusters: Dict[str, List[str]], factor: float = 0.5
) -> float:
    """Return a multiplier in (0, 1] reducing score for clustered addresses.

    factor controls how much the score is reduced per extra member.
    """
    for root, members in clusters.items():
        if address in members:
            size = len(members)
            if size <= 1:
                return 1.0
            if factor == 0:
                return 1.0
            penalty = max(0.0, 1.0 - factor * (size - 1) / 10)
            return penalty
    return 1.0
