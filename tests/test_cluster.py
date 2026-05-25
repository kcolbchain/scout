"""Tests for wallet clustering."""

from scout.cluster import build_clusters, cluster_penalty, UnionFind


def test_union_find_basic():
    uf = UnionFind()
    uf.union("a", "b")
    uf.union("c", "d")
    uf.union("a", "c")
    assert uf.find("a") == uf.find("d")
    assert uf.find("b") == uf.find("c")
    assert uf.find("a") != uf.find("z")


def test_union_find_isolated():
    uf = UnionFind()
    uf.union("a", "b")
    assert uf.find("c") != uf.find("a")


def test_shared_funder_edge():
    """Two addresses funded by same EOA with 5+ ETH each."""
    txs = [
        {"from": "0xfunder", "to": "0xa", "value": 10, "block": 1, "timestamp": 100000},
        {"from": "0xfunder", "to": "0xb", "value": 10, "block": 2, "timestamp": 100100},
    ]
    clusters = build_clusters(txs)
    merged = False
    for members in clusters.values():
        if "0xa" in members and "0xb" in members:
            merged = True
    assert merged


def test_dust_fan_out_edge():
    """EOA sending <5 ETH to 10+ addresses forms a cluster."""
    txs = [
        {"from": "0xduster", "to": f"0x{i:040x}", "value": 0.1, "block": 1, "timestamp": 100000}
        for i in range(12)
    ]
    clusters = build_clusters(txs)
    duster_root = None
    for root, members in clusters.items():
        if "0xduster" in members:
            duster_root = root
    assert duster_root is not None
    assert len(clusters[duster_root]) >= 11


def test_cluster_penalty_no_cluster():
    assert cluster_penalty("0xsolo", {}) == 1.0


def test_cluster_penalty_reduces_score():
    clusters = {"root": ["root", "a", "b"]}
    assert cluster_penalty("root", clusters, factor=0.5) < 1.0
    assert cluster_penalty("root", clusters, factor=0.5) > 0.0


def test_cluster_penalty_solo_member():
    clusters = {"root": ["root"]}
    assert cluster_penalty("root", clusters) == 1.0


def test_no_clustering_for_different_funders():
    """Addresses funded by different EOAs do not cluster."""
    txs = [
        {"from": "0xfunder_a", "to": "0xalice", "value": 10, "block": 1, "timestamp": 100000},
        {"from": "0xfunder_b", "to": "0xbob", "value": 10, "block": 2, "timestamp": 100100},
    ]
    clusters = build_clusters(txs)
    for members in clusters.values():
        assert not ("0xalice" in members and "0xbob" in members)
