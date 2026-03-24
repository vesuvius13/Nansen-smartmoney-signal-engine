# Nansen Smart Money Signal Engine — Full Writeup

## What Is This?

Most crypto traders look at one signal at a time — price, volume, or maybe a whale alert.
This tool does something different: it pulls **16 separate Nansen data streams in one run**,
cross-references them, and outputs a single ranked **Conviction Score (0–100)** for each token —
telling you not just *what* smart money is buying, but *how confident* the signal is.

Built entirely on the **Nansen CLI** (`nansen-cli`), with AI synthesis powered by **Claude**.

---

## The Problem It Solves

On-chain data is noisy. A token can show up in the token screener because of bot volume.
Smart money netflow can be positive because one fund is exiting a position, not entering.
Any single signal in isolation is unreliable.

The Smart Money Signal Engine solves this by requiring **multiple independent signals to agree**
before surfacing a token. If smart traders are flowing in, the token is in top SM holdings,
Nansen's own indicators are bullish, and price momentum confirms — that's a high-conviction setup.
If only one signal fires, the score stays low.

---

## How It Works — The 16-Call Pipeline

The pipeline has two tiers: **5 market-level calls** that run once, and **3 per-token calls**
that repeat for each token analysed (3 tokens = 9 calls). Together with the wallet profile and
cross-chain step, the total is always 16 calls for a standard 3-token scan.

```
── Market Level (5 calls) ───────────────────────────────────────────────────

Step 0   nansen account
         Checks API key validity and remaining credits before spending any.

Step 1   nansen research token screener --chain <chain> --timeframe 24h
         Finds tokens with the highest recent activity. Stablecoins and
         wrapped assets (USDC, USDT, WETH, CBBTC, etc.) are automatically
         filtered out so results are always tradeable tokens.

Step 2   nansen research smart-money netflow --chain <chain>
         Reads net capital flow across all smart money wallets for 24h.
         Used to determine overall market posture (RISK-ON vs RISK-OFF)
         and to build a per-token netflow lookup for scoring.

Step 3   nansen research smart-money dex-trades --chain <chain> --labels Fund
         Captures real-time DEX trades made by Fund-labelled wallets.
         Used to count fund trade velocity per token.

Step 4   nansen research smart-money holdings --chain <chain>
         Reads the aggregate token holdings of all smart money wallets.
         Gives each token a "holdings rank" — #1 means it's the biggest
         position in smart money portfolios right now.

── Per-Token Loop (3 calls × N tokens) ──────────────────────────────────────

Step 5a  nansen research token who-bought-sold --chain <chain> --token <addr>
         Lists the top buyers and sellers by USD volume. Only Nansen-labeled
         wallets (identified entities) are treated as smart money signals.
         Unlabeled wallets are classified as retail. If no labeled buyer
         exists for a token, the engine flags it as Low Conviction — there
         is no point in profiling a random retail wallet.

Step 5b  nansen research token indicators --chain <chain> --token <addr>
         Returns Nansen's proprietary on-chain indicators — split into
         reward_indicators (bullish signals like trading-range breakouts)
         and risk_indicators (bearish signals like supply inflation).
         Each bullish reward adds +1 to the indicator score;
         each high-risk flag subtracts -1. These signals are entirely
         Nansen's own quant logic — we only count and weight them.

Step 5c  nansen research token flow-intelligence --chain <chain> --token <addr>
         Returns capital flows broken down by investor segment for this token:
         smart_trader, top_pnl, whale, public_figure, exchange, fresh_wallets.
         This is the highest-weighted signal in the scoring model (35%).

         Two patterns are monitored:
         1. smart_trader + top_pnl positive, whale negative — experienced
            traders accumulating while unsophisticated large holders exit.
            Classic high-conviction divergence.
         2. fresh_wallets positive AND smart_trader positive simultaneously —
            freshly funded wallets are often used to hide insider accumulation
            before announcements. When both fire together, the engine raises
            an Insider Signal flag.

── Post-Loop (3 calls) ───────────────────────────────────────────────────────

Step 6   nansen research profiler balance --address <top_smart_buyer>
         Profiles the largest Nansen-labeled buyer found across all scanned
         tokens (sorted by conviction score, highest first). Shows total
         portfolio value and top 3 holdings. Intentionally runs once —
         for the single highest-signal wallet — rather than per token,
         to avoid unnecessary credit spend.

         If no labeled buyer exists across any token, this step is skipped
         and a Low Conviction warning is displayed instead.

Step 7   nansen research smart-money netflow --chain <alt_chain>
         Runs the same netflow query on the other major chain (Ethereum
         if scanning Solana, and vice versa). If both chains are RISK-ON
         simultaneously, it suggests a macro environment rather than
         chain-specific noise.

Step 8   Claude AI synthesis
         All collected data is serialised to JSON and sent to Claude Opus.
         Claude produces a ≤300-word trading intelligence briefing:
         overall market posture, highest-conviction picks with specific
         numbers cited, SM vs retail divergence flags, risk factors,
         and one actionable sentence per token.
```

---

## The Conviction Score (0–100)

Each token receives a composite score built from five independent factors:

| Weight | Factor | What It Measures |
|--------|--------|-----------------|
| **35%** | SM Segment Flow | `smart_trader + top_pnl` net flow from `flow-intelligence`. Positive = experienced money accumulating. Normalised: $1M net = full score. |
| **25%** | Token Indicator Score | Count of bullish `reward_indicators` minus high-severity `risk_indicators` from `token indicators`. Nansen's own quant signals. |
| **15%** | Price Momentum | 24h price change from the token screener. Normalised: −20% → 0, +20% → full score. Confirms on-chain signal with price action. |
| **15%** | SM Holdings Rank | Position in the `smart-money holdings` leaderboard. Being the #1 SM holding is a 15/15; not in top 30 is 0. |
| **10%** | SM Netflow Momentum | Token-specific net flow from `smart-money netflow`. $500K+ net positive = full score. |

**Signal tiers:**

| Score | Label | Meaning |
|-------|-------|---------|
| 75–100 | STRONG BUY | All five factors aligned — rare, high conviction |
| 60–74 | BUY | Most factors positive, clear directional signal |
| 45–59 | WATCH | Mixed signals, worth monitoring |
| 30–44 | NEUTRAL | No clear edge |
| 0–29 | AVOID | Multiple bearish signals |

The key design choice: **no single factor can produce a STRONG BUY on its own**.
Even maxing out SM Segment Flow (35 pts) and Indicator Score (25 pts) only gets to 60.
You need price momentum, holdings rank, and netflow all pointing the same direction to reach 75+.

---

## Key Technical Decisions

**Why normalise each factor independently?**
Each Nansen endpoint returns values on completely different scales ($USD flows vs integer counts
vs percentage changes). Normalising each factor to 0–100 before applying weights ensures no
single noisy large number dominates the score.

**Why filter stablecoins and wrapped assets from the screener?**
The token screener ranks by volume/activity. Without filtering, USDC, USDT, WETH, and CBBTC
always appear at the top since they have massive liquidity. These carry no directional signal —
a trader holding USDC is not making a bet. The `_SKIP_SYMBOLS` set removes ~20 known
non-signal assets before taking the top N results.

**Why use `flow-intelligence` as the highest-weighted factor?**
`smart-money netflow` tells you aggregate SM direction, but `flow-intelligence` breaks it down
by investor *quality* — smart traders vs whales vs fresh wallets. A token with strong
`smart_trader + top_pnl` flow but negative `whale` flow is the most interesting setup:
experienced, historically profitable wallets are accumulating while larger but less
sophisticated capital exits. This divergence is exactly the kind of edge that precedes moves.

**Why only profile Nansen-labeled buyers?**
The `who-bought-sold` endpoint returns any wallet by volume — most have no label. Profiling an
unlabeled retail wallet tells you nothing. The engine only passes Nansen-identified entities
(Jump Trading, Multicoin Capital, etc.) to the profiler step. If no labeled buyer exists
across any scanned token, the engine raises a Low Conviction flag instead of wasting a
credit on a meaningless profile.

**Why monitor fresh wallet flow as a separate signal?**
Nansen's `flow-intelligence` includes `fresh_wallets_net_flow_usd` — capital entering from
newly funded wallets. In isolation this can be noise. But when `fresh_wallet` flow is positive
*at the same time* as `smart_trader` flow, it suggests coordinated activity: insiders spinning
up new wallets to hide accumulation before a major announcement. The engine surfaces this as
an explicit Insider Signal flag in the output.

**Known model limitation — whale flow treatment:**
The current model uses `whale_net_flow_usd` only as a divergence signal (whale selling while
SM buys = high conviction). However, many Nansen "Whale" tags belong to highly sophisticated
institutional players whose buying can itself be the trigger for a major move. A future version
could add an alignment bonus when whale flow and smart_trader flow point in the same direction.

**Why cross-chain comparison?**
Capital rotates between Solana and Ethereum. If both chains show RISK-ON smart money posture
simultaneously, it suggests a macro risk-on environment rather than chain-specific noise.
If one is RISK-ON and the other RISK-OFF, the signal is weaker.

---

## Output

**Terminal** — rich-formatted table with colour-coded scores, per-factor breakdown bars,
Insider Signal / Low Conviction flags per token, wallet profile, and (if `ANTHROPIC_API_KEY`
is set) Claude's analysis in a yellow panel.

**Markdown report** — auto-saved to `nansen_report.md` with all scores, breakdowns, and
AI analysis in a shareable format.

---

## Usage

```bash
# Install
npm install -g nansen-cli
pip install rich anthropic

# Authenticate
nansen login --api-key YOUR_NANSEN_KEY
export ANTHROPIC_API_KEY=your_anthropic_key

# Run
python smart_money_scanner.py                   # Solana, top 3 tokens
python smart_money_scanner.py --chain ethereum  # Ethereum
python smart_money_scanner.py --tokens 5        # Analyse top 5 tokens
python smart_money_scanner.py --no-ai           # Skip Claude synthesis
python smart_money_scanner.py --mock            # Demo with synthetic data
```

---

## Tech Stack

| Tool | Role |
|------|------|
| `nansen-cli` | All on-chain data — 16 API calls per run |
| `anthropic` (Claude Opus) | AI narrative synthesis of aggregated signals |
| `rich` | Terminal UI — tables, panels, progress bars |
| Python 3.10+ | Orchestration, scoring, normalisation |

---

*Built for the Nansen CLI Challenge (Week 2) · #NansenCLI · @nansen_ai*
