# Nansen Smart Money Signal Engine

> **Built for the Nansen CLI Challenge (Week 2)**
> Cross-references 16 on-chain data sources to find where funds are moving **before** the market catches up.

---

## What it does

Most traders look at one signal — price or volume. This tool fuses **5 independent Nansen data streams** into a single **Conviction Score (0–100)** for each token:

| Weight | Factor | Nansen Endpoint |
|--------|--------|-----------------|
| 30% | Smart Money Buy Pressure | `token who-bought-sold` |
| 25% | Flow Momentum (last 3h) | `token flow-intelligence` |
| 20% | Price Momentum | `token indicators` |
| 15% | Fund Trade Velocity | `smart-money dex-trades` |
| 10% | SM Holdings Rank | `smart-money holdings` |

Then Claude AI synthesises everything into a plain-English trading briefing.

---

## Pipeline (16 API calls)

```
Step 0   nansen account                          ← check credits
Step 1   token screener                          ← find trending tokens (24h)
Step 2   smart-money netflow (primary chain)     ← is market risk-on or risk-off?
Step 3   smart-money dex-trades (Fund label)     ← what are funds buying RIGHT NOW?
Step 4   smart-money holdings                    ← what do funds already hold?
Step 5–7 Per token (×N tokens):
           token who-bought-sold                 ← SM% of buy flow
           token indicators                      ← momentum metrics
           token flow-intelligence               ← hourly SM vs retail flows
Step 8   profiler balance (top buyer wallet)     ← who is the biggest buyer?
Step 9   smart-money netflow (alt chain)         ← cross-chain posture comparison
Step 10  Claude AI synthesis                     ← narrative signal report
```

---

## Quick start

```bash
# 1. Install dependencies
npm install -g nansen-cli
pip install rich anthropic

# 2. Authenticate
nansen login --api-key YOUR_NANSEN_KEY
export ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY   # optional — for AI synthesis

# 3. Run
python smart_money_scanner.py                  # Solana, top 3 tokens
python smart_money_scanner.py --chain ethereum # Ethereum
python smart_money_scanner.py --tokens 5       # Analyse top 5 tokens
python smart_money_scanner.py --mock           # Demo mode (no API key needed)
python smart_money_scanner.py --no-ai          # Skip Claude synthesis
```

---

## Example output

```
╭────────────────────────────── Market Overview ───────────────────────────────╮
│    Chain       : SOLANA                                                      │
│    SM Posture  : RISK-ON 🟢  vs  ETHEREUM [RISK-ON 🟢]                      │
│    SM Inflow   : $19.20M  |  Outflow: $6.10M                                │
│    Fund Trades : 47 captured in 24h                                          │
╰──────────────────────────────────────────────────────────────────────────────╯

 Token Conviction Scores — SOLANA
╭──────┬──────────┬──────────┬────────┬────────────┬───────┬────────────╮
│ Rank │  Token   │  Price   │  24h % │ SM Netflow │ Score │   Signal   │
├──────┼──────────┼──────────┼────────┼────────────┼───────┼────────────┤
│  1   │  JUP     │  $0.72   │  +8.4% │   $3.10M   │  82   │ STRONG BUY │
│  2   │  BONK    │  $0.000… │ +14.7% │   $1.80M   │  71   │    BUY     │
│  3   │  WEN     │  $0.001… │ +22.1% │   $950K    │  48   │   WATCH    │
╰──────┴──────────┴──────────┴────────┴────────────┴───────┴────────────╯

JUP score breakdown:
  sm_buy_pressure      [████████████░░░░░░░░] 24.1/30
  flow_momentum        [████████████████████] 25.0/25
  price_momentum       [██████████████░░░░░░] 14.2/20
  sm_velocity          [████████░░░░░░░░░░░░]  8.0/15
  holdings_rank        [███████████████████░]  9.5/10
```

**Claude AI Analysis:**
> **SOLANA — RISK-ON**
> Smart money is net-buying $13.1M vs $6.1M out — funds are rotating INTO Solana.
> **JUP** is the highest-conviction pick: 3 Fund-labelled wallets added $375K in the last 8h while retail was net-selling. Flow momentum is accelerating.
> **Risk:** Volume spike could be liquidation-driven; check RSI before sizing up.
> *Action: JUP — accumulate on dips toward $0.68. BONK — hold existing positions.*

---

## Why this wins

1. **Creativity** — Multi-factor scoring model, not just a screener wrapper
2. **Usefulness** — Actionable output traders can act on immediately
3. **Technical depth** — 16 coordinated API calls, conviction scoring model, Claude synthesis
4. **Clear presentation** — Rich terminal UI + auto-saved markdown report

---

*Built with [Nansen CLI](https://agents.nansen.ai) · #NansenCLI · @nansen_ai*
