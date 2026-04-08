"""scout CLI — query the registry, score wallets, follow alpha.

Usage:
    python -m scout targets [--category l2] [--chain ethereum] [--confidence high]
    python -m scout get <name>
    python -m scout categories
    python -m scout follow [--chain ethereum]            # refresh + show alpha wallet signals
    python -m scout signals                              # protocol signals from last refresh
"""

from __future__ import annotations

import argparse
import sys

from .registry import Confidence, Registry
from .activity import WalletTracker


def _print_target_row(idx: int, t) -> None:
    icon = {"high": "🟢", "medium": "🟡", "low": "🔴", "claimed": "⚪"}.get(t.confidence.value, "•")
    print(f"{idx:>3}  {t.priority_score:>4.1f}  {icon} {t.confidence.value:<8}  "
          f"{t.chain:<10}  {t.category:<10}  {t.name}")


def cmd_targets(args: argparse.Namespace) -> int:
    reg = Registry.load()
    confidence = Confidence(args.confidence) if args.confidence else None
    targets = reg.filter(
        chain=args.chain,
        category=args.category,
        confidence=confidence,
        tag=args.tag,
    )
    if not targets:
        print("No targets match.")
        return 1
    print(f"\n{'#':>3}  {'Score':>5}  {'Confidence':>10}  {'Chain':<10}  {'Category':<10}  Name")
    print("─" * 78)
    for i, t in enumerate(targets, 1):
        _print_target_row(i, t)
    print(f"\n{len(targets)} target(s)")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    reg = Registry.load()
    t = reg.get(args.name)
    if t is None:
        print(f"No target named {args.name!r}")
        return 1
    print(f"\n{t.name}")
    print(f"  chain:      {t.chain}")
    print(f"  category:   {t.category}")
    print(f"  confidence: {t.confidence.value}")
    print(f"  priority:   {t.priority_score}")
    if t.tags:
        print(f"  tags:       {', '.join(t.tags)}")
    if t.contracts:
        print(f"  contracts:")
        for c in t.contracts:
            print(f"    - {c}")
    if t.criteria:
        print(f"  criteria:")
        for k, v in t.criteria.items():
            print(f"    {k}: {v}")
    if t.notes:
        print(f"  notes:      {t.notes}")
    return 0


def cmd_categories(args: argparse.Namespace) -> int:
    reg = Registry.load()
    for c in reg.categories():
        n = len(reg.filter(category=c))
        print(f"  {c:<12} {n}")
    return 0


def cmd_follow(args: argparse.Namespace) -> int:
    tracker = WalletTracker.load_alpha()
    chains = args.chain.split(",") if args.chain else None
    print(f"Refreshing {len(tracker.wallets)} alpha wallets across {chains or tracker.DEFAULT_CHAINS}...")
    try:
        tracker.refresh_sync(chains=chains, limit=args.limit)
    except Exception as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 2

    print("\nProtocol signals (top 20):")
    for proto, n in list(tracker.protocol_signals().items())[:20]:
        print(f"  {n:>4}  {proto}")
    print("\nChain signals:")
    for chain, n in tracker.chain_signals().items():
        print(f"  {n:>4}  {chain}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scout", description="On-chain wallet & protocol intelligence")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_targets = sub.add_parser("targets", help="List registered targets")
    p_targets.add_argument("--category")
    p_targets.add_argument("--chain")
    p_targets.add_argument("--confidence", choices=[c.value for c in Confidence])
    p_targets.add_argument("--tag")
    p_targets.set_defaults(func=cmd_targets)

    p_get = sub.add_parser("get", help="Show details for one target")
    p_get.add_argument("name")
    p_get.set_defaults(func=cmd_get)

    p_cat = sub.add_parser("categories", help="List categories with counts")
    p_cat.set_defaults(func=cmd_categories)

    p_follow = sub.add_parser("follow", help="Refresh alpha wallets, show signals")
    p_follow.add_argument("--chain", help="Comma-separated chain names")
    p_follow.add_argument("--limit", type=int, default=20)
    p_follow.set_defaults(func=cmd_follow)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
