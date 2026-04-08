"""Target registry — a queryable database of protocols and their metadata.

A Target is any protocol you want to track for any reason: airdrops, due
diligence, governance participation, treasury monitoring, market intel, etc.

Data lives in YAML at scout/data/targets.yaml so it can be edited, versioned,
and contributed to without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Iterable, Optional

import yaml

logger = logging.getLogger(__name__)


class Confidence(Enum):
    """How confident we are in the target's near-term relevance."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CLAIMED = "claimed"  # for airdrops; "completed" / "shipped" for other categories


_CONFIDENCE_RANK = {
    Confidence.CLAIMED: 0,
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
}


@dataclass
class Target:
    """A tracked protocol. Generic enough for any intelligence use case."""

    name: str
    chain: str  # single chain id, or "multi" for cross-chain
    category: str  # bridge, dex, lending, l2, infra, defi, nft, social, ...
    confidence: Confidence = Confidence.MEDIUM
    contracts: list[str] = field(default_factory=list)
    criteria: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    priority_score: float = 0.0  # 0-10, manually curated or computed
    last_updated: Optional[datetime] = None

    def matches(
        self,
        chain: Optional[str] = None,
        category: Optional[str] = None,
        confidence: Optional[Confidence] = None,
        tag: Optional[str] = None,
    ) -> bool:
        if chain and self.chain != chain and self.chain != "multi":
            return False
        if category and self.category != category:
            return False
        if confidence and _CONFIDENCE_RANK[self.confidence] < _CONFIDENCE_RANK[confidence]:
            return False
        if tag and tag not in self.tags:
            return False
        return True


class Registry:
    """A queryable collection of Targets."""

    def __init__(self, targets: Optional[list[Target]] = None):
        self.targets: list[Target] = list(targets or [])
        self._sort()

    # ---------- loading ----------

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Registry":
        """Load the bundled curated registry, or a custom YAML file."""
        if path is None:
            data_text = resources.files("scout").joinpath("data/targets.yaml").read_text()
        else:
            data_text = Path(path).read_text()
        raw = yaml.safe_load(data_text) or {}
        targets = [cls._target_from_dict(d) for d in raw.get("targets", [])]
        return cls(targets)

    @staticmethod
    def _target_from_dict(d: dict) -> Target:
        return Target(
            name=d["name"],
            chain=d.get("chain", "multi"),
            category=d.get("category", "other"),
            confidence=Confidence(d.get("confidence", "medium")),
            contracts=d.get("contracts", []) or [],
            criteria=d.get("criteria", {}) or {},
            tags=d.get("tags", []) or [],
            notes=d.get("notes", ""),
            priority_score=float(d.get("priority_score", 0.0)),
            last_updated=datetime.utcnow(),
        )

    # ---------- queries ----------

    def get(self, name: str) -> Optional[Target]:
        for t in self.targets:
            if t.name.lower() == name.lower():
                return t
        return None

    def filter(
        self,
        chain: Optional[str] = None,
        category: Optional[str] = None,
        confidence: Optional[Confidence] = None,
        tag: Optional[str] = None,
    ) -> list[Target]:
        return [
            t for t in self.targets
            if t.matches(chain=chain, category=category, confidence=confidence, tag=tag)
        ]

    def categories(self) -> list[str]:
        return sorted({t.category for t in self.targets})

    def chains(self) -> list[str]:
        return sorted({t.chain for t in self.targets})

    # ---------- mutation ----------

    def add(self, target: Target) -> None:
        self.targets.append(target)
        self._sort()

    def mark(self, name: str, confidence: Confidence) -> bool:
        t = self.get(name)
        if t is None:
            return False
        t.confidence = confidence
        t.last_updated = datetime.utcnow()
        self._sort()
        return True

    def _sort(self) -> None:
        self.targets.sort(key=lambda t: (-t.priority_score, t.name))

    # ---------- iteration ----------

    def __iter__(self) -> Iterable[Target]:
        return iter(self.targets)

    def __len__(self) -> int:
        return len(self.targets)
