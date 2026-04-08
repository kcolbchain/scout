# scout

> On-chain wallet and protocol intelligence primitives. Registry, fit scoring, activity tracking.

`scout` is a small Python library for systematic on-chain research. Three composable parts:

- **Registry** — a curated, queryable database of protocols (Targets) with metadata: chain, category, confidence, criteria, contracts, notes, priority. Loaded from YAML so you can edit, fork, and contribute without code changes.
- **FitScorer** — scores any wallet against any target's criteria (0–100 with met / missing / recommendations breakdown). Works for airdrop eligibility, allowlist gating, lending risk, KYC-lite reputation — anywhere you ask "does this wallet match these requirements?"
- **WalletTracker** — follows a set of wallets across chains, aggregates protocol signals. Etherscan v2 backend by default, pluggable for Alchemy / Covalent / your own indexer.

By [kcolbchain](https://kcolbchain.com) (est. 2015). The intelligence layer that powers [monsoon](https://github.com/kcolbchain/monsoon) airdrop research, but useful far beyond airdrops.

## Why scout?

Wallet and protocol intelligence shows up in a lot of places that pretend to be unrelated:

- Airdrop research: which wallets qualify for which drops?
- Due diligence: which wallets actually use this protocol?
- Treasury monitoring: which protocols does this whale prefer?
- Wallet reputation: is this address a real user or a sybil?
- Allowlist gating: does this wallet meet our criteria?
- Governance intel: where is this delegate active?
- Ecosystem mapping: which protocols share user bases?

The shape of the problem is the same in all cases: you need a registry of protocols, a way to ask "does wallet X fit target Y's criteria," and a way to follow wallets across chains. scout gives you those primitives without coupling them to any single use case.

## Install

```bash
pip install scout-onchain
# or for full activity tracking (Etherscan v2 fetcher):
pip install scout-onchain[activity]
```

## Quick start

```python
from scout import Registry, FitScorer, WalletTracker

# 1. Load the curated registry of protocols
reg = Registry.load()
print(f"Loaded {len(reg)} targets across {len(reg.categories())} categories")

# 2. Filter
l2_targets = reg.filter(category="l2", confidence="high")
for t in l2_targets:
    print(t.name, t.chain, t.priority_score)

# 3. Score a wallet against a target
scorer = FitScorer()
linea = reg.get("Linea")
score = scorer.score(my_wallet, linea)
print(f"{score.target}: {score.score}/100 ({score.grade})")
print("Met:", score.met)
print("Missing:", score.missing)
print("Recommendations:", score.recommendations)

# 4. Follow alpha wallets across chains
import asyncio
tracker = WalletTracker.load_alpha()
asyncio.run(tracker.refresh(chains=["ethereum", "arbitrum", "base"]))
print("Top protocols by smart-money activity:")
for proto, n in list(tracker.protocol_signals().items())[:10]:
    print(f"  {n:>3}  {proto}")
```

## CLI

```bash
# List targets
python -m scout targets
python -m scout targets --category l2 --confidence high
python -m scout targets --chain ethereum

# Inspect one target
python -m scout get Linea

# Available categories
python -m scout categories

# Refresh alpha wallets and dump signals
ETHERSCAN_API_KEY=YOUR_KEY python -m scout follow
```

## Data files

The curated assets live in [`scout/data/`](scout/data/) as YAML so they can be edited, versioned, and contributed:

- [`targets.yaml`](scout/data/targets.yaml) — protocol registry
- [`alpha_wallets.yaml`](scout/data/alpha_wallets.yaml) — wallets worth following
- [`known_contracts.yaml`](scout/data/known_contracts.yaml) — address → protocol mapping

PRs adding entries are welcome. Keep entries factual; cite a source in `notes` when possible.

## What scout is *not*

- **Not a trading bot.** scout is read-only intelligence; it never signs or broadcasts transactions.
- **Not an airdrop farmer.** monsoon is the farming agent; scout is the research substrate it consumes.
- **Not a graph database.** Single Python module, YAML data, no service to run.
- **Not opinionated about backends.** Etherscan v2 is the default but `ActivityBackend` is a 3-line interface — plug in whatever you want.

## Used by

- [monsoon](https://github.com/kcolbchain/monsoon) — autonomous airdrop farming agents
- (your project here — open a PR)

## License

MIT — see [LICENSE](LICENSE).
