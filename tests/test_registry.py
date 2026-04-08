"""Tests for the Registry."""

import pytest

from scout import Registry, Target, Confidence


def test_load_bundled_registry():
    reg = Registry.load()
    assert len(reg) > 0
    assert all(isinstance(t, Target) for t in reg)


def test_get_by_name_case_insensitive():
    reg = Registry.load()
    t = reg.get("Linea")
    assert t is not None
    assert reg.get("linea") is t
    assert reg.get("LINEA") is t


def test_filter_by_category():
    reg = Registry.load()
    l2s = reg.filter(category="l2")
    assert len(l2s) > 0
    assert all(t.category == "l2" for t in l2s)


def test_filter_by_confidence():
    reg = Registry.load()
    high = reg.filter(confidence=Confidence.HIGH)
    assert len(high) > 0
    assert all(t.confidence == Confidence.HIGH for t in high)


def test_filter_chain_multi_matches_any():
    reg = Registry.load()
    eth_targets = reg.filter(chain="ethereum")
    # LayerZero is chain="multi" and should match any chain query
    layerzero = reg.get("LayerZero")
    assert layerzero is not None
    assert layerzero in eth_targets


def test_priority_score_sorting():
    reg = Registry.load()
    scores = [t.priority_score for t in reg]
    assert scores == sorted(scores, reverse=True)


def test_categories_unique_and_sorted():
    reg = Registry.load()
    cats = reg.categories()
    assert cats == sorted(set(cats))


def test_mark_changes_confidence():
    reg = Registry.load()
    name = next(iter(reg)).name
    assert reg.mark(name, Confidence.CLAIMED)
    assert reg.get(name).confidence == Confidence.CLAIMED


def test_add_target():
    reg = Registry.load()
    n_before = len(reg)
    reg.add(Target(name="TestProto", chain="ethereum", category="dex", priority_score=5.0))
    assert len(reg) == n_before + 1
    assert reg.get("TestProto") is not None
