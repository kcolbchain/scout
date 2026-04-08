"""Tests for FitScorer."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from scout import FitScorer, Target, Confidence


@dataclass
class FakeActivity:
    chain: str
    action: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FakeWallet:
    address: str = "0xtest"
    activity: list = field(default_factory=list)
    _gas: float = 0.0

    @property
    def total_gas_spent(self):
        return self._gas

    @property
    def unique_days_active(self):
        return len({a.timestamp.date() for a in self.activity})

    @property
    def unique_protocols(self):
        return {f"p{i}" for i in range(len(self.activity))}


def make_target(criteria=None) -> Target:
    return Target(
        name="TestL2",
        chain="testnet",
        category="l2",
        confidence=Confidence.HIGH,
        criteria=criteria or {},
    )


def test_empty_wallet_scores_zero():
    scorer = FitScorer()
    score = scorer.score(FakeWallet(), make_target())
    assert score.score == 0.0
    assert score.grade == "F"


def test_bridge_criteria_awards_15():
    scorer = FitScorer()
    wallet = FakeWallet(activity=[
        FakeActivity("ethereum", "Bridge 0.01 ETH ethereum->arbitrum") for _ in range(3)
    ])
    target = make_target(criteria={"bridge_volume": ">0.1 ETH"})
    score = scorer.score(wallet, target)
    assert any("Bridge activity" in m for m in score.met)
    assert score.score >= 15


def test_dex_criteria_awards_15():
    scorer = FitScorer()
    wallet = FakeWallet(activity=[
        FakeActivity("arbitrum", "Swap 0.01 ETH for USDC") for _ in range(5)
    ])
    target = make_target(criteria={"dex_swaps": ">5"})
    score = scorer.score(wallet, target)
    assert any("DEX swaps" in m for m in score.met)


def test_chain_diversity_bonus():
    scorer = FitScorer()
    wallet = FakeWallet(activity=[
        FakeActivity("ethereum", "Swap"),
        FakeActivity("arbitrum", "Swap"),
        FakeActivity("base", "Swap"),
    ])
    score = scorer.score(wallet, make_target())
    assert any("Chain diversity" in m for m in score.met)


def test_long_term_user_bonus():
    scorer = FitScorer()
    base = datetime(2026, 1, 1)
    activity = [
        FakeActivity("ethereum", f"Swap day {i}", timestamp=base + timedelta(days=i))
        for i in range(35)
    ]
    wallet = FakeWallet(activity=activity)
    score = scorer.score(wallet, make_target())
    assert any("Long-term user" in m for m in score.met)


def test_score_capped_at_100():
    scorer = FitScorer()
    base = datetime(2026, 1, 1)
    activity = [
        FakeActivity(c, "Swap on uniswap", timestamp=base + timedelta(days=i))
        for i, c in enumerate(["ethereum", "arbitrum", "base", "optimism"] * 10)
    ]
    wallet = FakeWallet(activity=activity, _gas=1.0)
    target = make_target(criteria={
        "bridge_volume": ">0.1",
        "dex_swaps": ">5",
        "unique_months": ">3",
    })
    score = scorer.score(wallet, target)
    assert score.score <= 100.0


def test_score_grades():
    scorer = FitScorer()
    fake_score = scorer.score(FakeWallet(), make_target())
    fake_score.score = 85
    assert fake_score.grade == "A"
    fake_score.score = 65
    assert fake_score.grade == "B"
    fake_score.score = 45
    assert fake_score.grade == "C"
