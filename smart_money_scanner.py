#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          Nansen Smart Money Signal Engine  •  github.com/sagarkhanna         ║
║  Cross-references 10+ on-chain sources to find where funds are moving        ║
║  BEFORE the market catches up.                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

Pipeline  (each step = 1+ Nansen API calls):
  1.  Account check           → verify credits
  2.  Token screener          → find tokens with unusual smart-money activity
  3.  SM netflow              → overall market direction (are funds net-buying?)
  4.  SM DEX trades           → real-time fund buy/sell velocity
  5.  SM holdings             → what funds are already holding
  6-8. Per-token deep-dive    → who-bought-sold, indicators, flow-intelligence
  9.  Wallet profile          → identity check on the top buyer
  10. Cross-chain compare     → same sector on Ethereum vs Solana
  11. AI synthesis            → Claude converts data → narrative signals

Usage:
    python smart_money_scanner.py                          # Solana, top 3 tokens
    python smart_money_scanner.py --chain ethereum         # Switch chain
    python smart_money_scanner.py --tokens 5               # Analyse top 5 tokens
    python smart_money_scanner.py --mock                   # Run on mock data (no API key needed)
    python smart_money_scanner.py --no-ai                  # Skip Claude synthesis

Requirements:
    pip install rich anthropic
    npm install -g nansen-cli
    nansen login --api-key YOUR_KEY   (or export NANSEN_API_KEY=...)
    export ANTHROPIC_API_KEY=...      (for AI synthesis; optional with --no-ai)
"""

import subprocess
import json
import sys
import argparse
import os
import time
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
import anthropic
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.rule import Rule

console = Console()
API_CALL_LOG: list[dict] = []


def extract_rows(response: dict) -> list:
    """
    Nansen CLI responses come in two shapes:
      • flat:   {"success": true, "data": [...]}
      • nested: {"success": true, "data": {"data": [...], "pagination": {...}}}
    This helper normalises both into a plain list.
    """
    data = response.get("data", [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        inner = data.get("data", [])
        if isinstance(inner, list):
            return inner
    return []


def screener_field(tok: dict, *keys: str, default=None):
    """Try multiple field name variants in order — screener uses different names than mock."""
    for k in keys:
        v = tok.get(k)
        if v is not None:
            return v
    return default


# ──────────────────────────────────────────────────────────────────────────────
# Nansen CLI wrapper
# ──────────────────────────────────────────────────────────────────────────────

def nansen(args: list[str], *, label: str = "", retries: int = 2) -> dict:
    """
    Run a nansen CLI command and return the parsed JSON response.
    Logs every call for the summary table shown at the end.
    Exits immediately on CREDITS_EXHAUSTED.
    """
    cmd = ["nansen"] + args
    full_cmd = " ".join(cmd)
    started = time.time()

    for attempt in range(retries + 1):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            raw = result.stdout.strip()

            if not raw:
                err = result.stderr.strip() or "No output"
                data = {"success": False, "error": err}
            else:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"success": False, "error": "JSON parse error", "raw": raw[:300]}

            elapsed = round(time.time() - started, 2)
            status = "✓" if data.get("success") else "✗"
            API_CALL_LOG.append({"cmd": full_cmd, "label": label or " ".join(args[:3]),
                                  "status": status, "elapsed": elapsed})

            if not data.get("success"):
                code = data.get("code", "")
                if code == "CREDITS_EXHAUSTED":
                    console.print("\n[bold red]✗ CREDITS_EXHAUSTED — halting to protect your balance.[/bold red]")
                    _print_api_log()
                    sys.exit(1)
                if code == "RATE_LIMITED" and attempt < retries:
                    console.print(f"  [yellow]Rate limited, retrying in 2s…[/yellow]")
                    time.sleep(2)
                    continue

            return data
        except subprocess.TimeoutExpired:
            elapsed = 45
            API_CALL_LOG.append({"cmd": full_cmd, "label": label, "status": "✗ timeout", "elapsed": elapsed})
            return {"success": False, "error": "Timeout after 45s"}
        except Exception as e:
            API_CALL_LOG.append({"cmd": full_cmd, "label": label, "status": "✗ err", "elapsed": 0})
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "Max retries exceeded"}


# ──────────────────────────────────────────────────────────────────────────────
# Mock data (--mock flag lets you demo without an API key)
# ──────────────────────────────────────────────────────────────────────────────

def _mock_call(label: str, latency: float = 0.3) -> None:
    """Record a simulated API call in the log (for --mock demo mode)."""
    API_CALL_LOG.append({"cmd": f"nansen {label}", "label": label, "status": "✓ (mock)", "elapsed": latency})

def _mock_screener() -> dict:
    return {"success": True, "data": [
        {"token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
         "symbol": "JUP", "name": "Jupiter", "price_usd": 0.72,
         "price_change_24h_pct": 8.4, "volume_24h_usd": 48_200_000,
         "smart_money_netflow_24h_usd": 3_100_000, "market_cap_usd": 980_000_000,
         "smart_money_buyers_count": 47, "smart_money_sellers_count": 12},
        {"token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
         "symbol": "BONK", "name": "Bonk", "price_usd": 0.0000198,
         "price_change_24h_pct": 14.7, "volume_24h_usd": 92_100_000,
         "smart_money_netflow_24h_usd": 1_800_000, "market_cap_usd": 1_400_000_000,
         "smart_money_buyers_count": 31, "smart_money_sellers_count": 9},
        {"token_address": "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk",
         "symbol": "WEN", "name": "Wen", "price_usd": 0.00152,
         "price_change_24h_pct": 22.1, "volume_24h_usd": 31_000_000,
         "smart_money_netflow_24h_usd": 950_000, "market_cap_usd": 152_000_000,
         "smart_money_buyers_count": 18, "smart_money_sellers_count": 4},
    ]}

def _mock_netflow() -> dict:
    return {"success": True, "data": [
        {"symbol": "SOL", "token_address": "So11111111111111111111111111111111111111112",
         "inflow_usd": 12_400_000, "outflow_usd": 4_200_000, "netflow_usd": 8_200_000},
        {"symbol": "JUP", "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
         "inflow_usd": 4_100_000, "outflow_usd": 1_000_000, "netflow_usd": 3_100_000},
        {"symbol": "BONK", "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
         "inflow_usd": 2_700_000, "outflow_usd": 900_000, "netflow_usd": 1_800_000},
    ]}

def _mock_dex_trades() -> dict:
    return {"success": True, "data": [
        {"wallet": "7Vz3kk7bzSmmZiMMrJqxHxbkFjTVH3fZ5yVLTdmBa9rW",
         "label": "Fund", "entity": "Jump Trading",
         "token_bought_symbol": "JUP", "token_bought_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
         "amount_usd": 280_000, "timestamp": "2026-03-23T08:12:00Z"},
        {"wallet": "3FH5T8BMQ9yqBATKXB3XDi9wR7BVsNMFBFKhv2GN2dkX",
         "label": "Smart Trader", "entity": None,
         "token_bought_symbol": "JUP", "token_bought_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
         "amount_usd": 95_000, "timestamp": "2026-03-23T07:44:00Z"},
        {"wallet": "9QgXqrgdbVU8KcpfskzmekLqH9CtKG7zQALXxoP3jQVn",
         "label": "Fund", "entity": "Multicoin Capital",
         "token_bought_symbol": "BONK", "token_bought_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
         "amount_usd": 440_000, "timestamp": "2026-03-23T07:01:00Z"},
        {"wallet": "ALjpYzFmTKdHFpR7Q2eBZGt8ZFnbP5nZuCsQEiTBgFKu",
         "label": "Fund", "entity": "Alameda Research",
         "token_bought_symbol": "WEN", "token_bought_address": "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk",
         "amount_usd": 180_000, "timestamp": "2026-03-23T06:30:00Z"},
    ]}

def _mock_holdings() -> dict:
    return {"success": True, "data": [
        {"symbol": "SOL", "token_address": "So11111111111111111111111111111111111111112",
         "total_value_usd": 340_000_000, "holder_count": 412},
        {"symbol": "JUP", "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
         "total_value_usd": 48_000_000, "holder_count": 89},
        {"symbol": "BONK", "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
         "total_value_usd": 29_000_000, "holder_count": 63},
    ]}

def _mock_who_bought(symbol: str) -> dict:
    return {"success": True, "data": {
        "smart_money_buy_volume_usd": 3_800_000,
        "smart_money_sell_volume_usd": 620_000,
        "retail_buy_volume_usd": 11_200_000,
        "retail_sell_volume_usd": 13_100_000,
        "top_buyers": [
            {"address": "7Vz3kk7bzSmmZiMMrJqxHxbkFjTVH3fZ5yVLTdmBa9rW",
             "label": "Fund", "entity": "Jump Trading", "volume_usd": 280_000},
            {"address": "3FH5T8BMQ9yqBATKXB3XDi9wR7BVsNMFBFKhv2GN2dkX",
             "label": "Smart Trader", "entity": None, "volume_usd": 95_000},
        ]
    }}

def _mock_indicators(symbol: str) -> dict:
    return {"success": True, "data": {
        "price_usd": 0.72, "price_change_24h_pct": 8.4,
        "price_change_7d_pct": 31.2,
        "volume_24h_usd": 48_200_000, "volume_change_24h_pct": 142,
        "smart_money_score": 74, "liquidity_usd": 9_800_000,
        "holder_count": 124_000, "age_days": 487
    }}

def _mock_flows(symbol: str) -> dict:
    return {"success": True, "data": [
        {"hour": "2026-03-23T06:00:00Z", "smart_money_inflow_usd": 1_200_000,
         "smart_money_outflow_usd": 180_000, "retail_inflow_usd": 3_800_000,
         "retail_outflow_usd": 4_200_000},
        {"hour": "2026-03-23T07:00:00Z", "smart_money_inflow_usd": 1_800_000,
         "smart_money_outflow_usd": 210_000, "retail_inflow_usd": 4_100_000,
         "retail_outflow_usd": 4_900_000},
        {"hour": "2026-03-23T08:00:00Z", "smart_money_inflow_usd": 900_000,
         "smart_money_outflow_usd": 90_000, "retail_inflow_usd": 2_200_000,
         "retail_outflow_usd": 2_900_000},
    ]}

def _mock_wallet_profile(address: str) -> dict:
    return {"success": True, "data": {
        "address": address, "labels": ["Fund"],
        "entity": "Jump Trading", "chain": "solana",
        "total_portfolio_usd": 14_800_000,
        "top_holdings": [
            {"symbol": "SOL", "value_usd": 8_200_000},
            {"symbol": "JUP", "value_usd": 3_100_000},
            {"symbol": "BONK", "value_usd": 1_400_000},
        ],
        "realized_pnl_30d_usd": 2_300_000
    }}

def _mock_eth_netflow() -> dict:
    return {"success": True, "data": [
        {"symbol": "ETH", "inflow_usd": 22_000_000, "outflow_usd": 8_000_000, "netflow_usd": 14_000_000},
        {"symbol": "WBTC", "inflow_usd": 18_000_000, "outflow_usd": 12_000_000, "netflow_usd": 6_000_000},
    ]}


# ──────────────────────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────────────────────

def _parse_flow_intelligence(flows: dict) -> dict:
    """
    flow-intelligence returns data.data[0] — a single row with segment net flows.
    Real fields: smart_trader_net_flow_usd, top_pnl_net_flow_usd, whale_net_flow_usd,
                 public_figure_net_flow_usd, exchange_net_flow_usd, fresh_wallets_net_flow_usd
    """
    rows = extract_rows(flows)
    if not rows:
        # mock data uses a list of hourly rows — sum smart_money fields
        rows_alt = flows.get("data", [])
        if isinstance(rows_alt, list) and rows_alt:
            st = sum(float(r.get("smart_money_inflow_usd", 0)) - float(r.get("smart_money_outflow_usd", 0))
                     for r in rows_alt)
            return {"smart_trader_net_flow_usd": st, "top_pnl_net_flow_usd": 0,
                    "whale_net_flow_usd": 0, "smart_trader_wallet_count": 0}
        return {}
    row = rows[0] if isinstance(rows[0], dict) else {}
    return row


def _parse_indicators(indicators: dict) -> dict:
    """
    token indicators: data is a dict (not nested data.data) with:
      token_info.is_stablecoin, risk_indicators[], reward_indicators[]
    Returns a normalised summary dict.
    """
    ind = indicators.get("data", {})
    if not isinstance(ind, dict):
        return {}
    reward = ind.get("reward_indicators", [])
    risk   = ind.get("risk_indicators",   [])
    # Score: +1 per bullish reward, -1 per high risk
    score = sum(1 for r in reward if r.get("score") == "bullish")
    score -= sum(1 for r in risk   if r.get("score") in ("high", "very_high"))
    is_stable = (ind.get("token_info") or {}).get("is_stablecoin", False)
    return {"indicator_score": score, "reward_count": len(reward),
            "risk_count": len(risk), "is_stablecoin": is_stable}


def conviction_score(
    who_bought: dict,
    indicators: dict,
    flows: dict,
    sm_netflow_24h_usd: float,
    sm_trader_count: int,
    sm_holding_rank: int,
    price_change_pct: float,
) -> tuple[float, dict]:
    """
    Multi-factor conviction score 0–100.

    Weight  Factor                    Source
    ──────  ────────────────────────  ─────────────────────────────
     35%    SM Segment Flow           flow-intelligence (smart_trader + top_pnl net)
     25%    Token Indicator Score     token indicators (bullish rewards − high risks)
     15%    Price Momentum            screener price_change
     15%    SM Holdings Rank          smart-money holdings position
     10%    SM Netflow Momentum       smart-money netflow net_flow_24h_usd
    """
    breakdown: dict[str, float] = {}

    # ── 1. SM Segment Flow (35%) ─────────────────────────
    fi = _parse_flow_intelligence(flows)
    sm_seg_flow = (float(fi.get("smart_trader_net_flow_usd", 0)) +
                   float(fi.get("top_pnl_net_flow_usd", 0)))
    # $1M net = full score; negative = 0
    flow_norm = min(max(sm_seg_flow / 1_000_000, -1.0), 1.0)
    breakdown["sm_segment_flow"] = ((flow_norm + 1) / 2) * 100 * 0.35

    # ── 2. Token Indicator Score (25%) ──────────────────
    ind_parsed = _parse_indicators(indicators)
    # ind_score ranges roughly -3..+5; normalise to 0-100
    ind_score = float(ind_parsed.get("indicator_score", 0))
    ind_norm = min(max((ind_score + 3) / 8, 0.0), 1.0) * 100
    breakdown["indicator_score"] = ind_norm * 0.25

    # ── 3. Price Momentum (15%) ─────────────────────────
    # Normalise: −20% → 0, +20% → 100
    price_norm = min(max((price_change_pct + 20) / 40, 0.0), 1.0) * 100
    breakdown["price_momentum"] = price_norm * 0.15

    # ── 4. SM Holdings Rank (15%) ───────────────────────
    if sm_holding_rank > 0:
        rank_norm = max(0.0, 1 - (sm_holding_rank - 1) / 30)
    else:
        rank_norm = 0.0
    breakdown["holdings_rank"] = rank_norm * 100 * 0.15

    # ── 5. SM Netflow Momentum (10%) ────────────────────
    nf_norm = min(max(sm_netflow_24h_usd / 500_000, -1.0), 1.0)
    breakdown["netflow_momentum"] = ((nf_norm + 1) / 2) * 100 * 0.10

    total = sum(breakdown.values())
    return round(total, 1), {k: round(v, 1) for k, v in breakdown.items()}


def score_to_label(score: float) -> tuple[str, str]:
    """(emoji label, rich colour) for a conviction score."""
    if score >= 75: return "STRONG BUY", "bold green"
    if score >= 60: return "BUY",         "green"
    if score >= 45: return "WATCH",       "yellow"
    if score >= 30: return "NEUTRAL",     "white"
    return "AVOID", "red"


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:.2f}"

def fmt_pct(v: float, with_sign: bool = True) -> str:
    s = f"{v:+.1f}%" if with_sign else f"{v:.1f}%"
    return s

def _bar(value: float, total: float = 100, width: int = 20) -> str:
    filled = int((value / total) * width) if total else 0
    return "█" * filled + "░" * (width - filled)

def _print_api_log():
    console.print()
    t = Table(title="API Calls Summary", box=box.SIMPLE_HEAD, show_lines=False)
    t.add_column("#", style="dim", width=3)
    t.add_column("Label", min_width=30)
    t.add_column("Status", justify="center", width=8)
    t.add_column("Elapsed", justify="right", width=8)
    for i, entry in enumerate(API_CALL_LOG, 1):
        status_style = "green" if entry["status"] == "✓" else "red"
        t.add_row(str(i), entry["label"], f"[{status_style}]{entry['status']}[/{status_style}]",
                  f"{entry['elapsed']}s")
    t.add_row("", f"[bold]Total calls: {len(API_CALL_LOG)}[/bold]", "", "")
    console.print(t)


def print_banner():
    console.print(Rule("[bold cyan]Nansen Smart Money Signal Engine[/bold cyan]", style="cyan"))
    console.print(f"  [dim]Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")
    console.print(f"  [dim]Powered by Nansen CLI + Claude AI[/dim]")
    console.print()


# ──────────────────────────────────────────────────────────────────────────────
# AI synthesis
# ──────────────────────────────────────────────────────────────────────────────

def ai_synthesis(chain: str, summary: dict) -> str:
    """
    Send the aggregated signal data to Claude and get a narrative analysis.
    Returns the analysis as a string.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "[yellow]Set ANTHROPIC_API_KEY to enable AI synthesis.[/yellow]"

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a senior on-chain analyst at a crypto hedge fund.
I have just run a multi-factor smart money scan on {chain.upper()} using Nansen data.

Here is the aggregated signal data (JSON):
{json.dumps(summary, indent=2)}

Please produce a concise (≤300 words) trading intelligence briefing that:
1. States the overall market posture on {chain.upper()} (risk-on / risk-off / neutral)
2. Highlights the 1–2 highest-conviction tokens and WHY (cite specific numbers)
3. Notes any divergence between smart money and retail (contrarian signal)
4. Flags any risk factor that could invalidate the thesis
5. Ends with one actionable sentence per top token

Tone: confident, data-driven, no fluff. Write in bullet points under short headers."""

    try:
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        return f"[red]AI synthesis error: {e}[/red]"


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(chain: str, top_n: int, mock: bool, skip_ai: bool, output: Optional[str]):

    print_banner()
    chain_upper = chain.upper()

    # ── Step 0 — account check ────────────────────────────────────────────────
    console.print(f"[bold]0.[/bold] Checking account status…")
    if mock:
        console.print("   [yellow]MOCK MODE — simulating API calls[/yellow]")
        acct = {"success": True, "data": {"plan": "Pro", "credits_remaining": 99_999}}
        _mock_call("account — credits check", 0.15)
    else:
        acct = nansen(["account"], label="account — credits check")
    if acct.get("success"):
        d = acct.get("data", {})
        console.print(f"   Plan: [cyan]{d.get('plan','?')}[/cyan]  |  "
                      f"Credits: [green]{d.get('credits_remaining','?')}[/green]")
    console.print()

    # ── Step 1 — Token screener ───────────────────────────────────────────────
    console.print(f"[bold]1.[/bold] Running token screener on {chain_upper}…")
    if mock:
        screener_raw = _mock_screener()
        _mock_call(f"research token screener --chain {chain} --timeframe 24h", 0.42)
    else:
        screener_raw = nansen(
            ["research", "token", "screener", "--chain", chain, "--timeframe", "24h", "--limit", "20"],
            label=f"token screener ({chain})")

    _SKIP_SYMBOLS = {
        # Stablecoins
        "USDC","USDT","DAI","BUSD","FDUSD","USDE","PYUSD","TUSD","USDP","GUSD","LUSD",
        "USDS","USD1","USDH","CUSD","SUSD","FRAX","USDX","USDD","CETUS",
        # Wrapped / liquid-staking (usually low alpha signal)
        "WETH","WBTC","WBNB","WSOL","CBBTC","STETH","WSTETH","RETH","CBETH",
    }
    all_screener = extract_rows(screener_raw)
    # Also use is_stablecoin flag when available
    tokens = [
        t for t in all_screener
        if screener_field(t, "token_symbol", "symbol", default="").upper() not in _SKIP_SYMBOLS
        and not (t.get("token_info") or {}).get("is_stablecoin", False)
    ][:top_n]
    if not tokens:
        console.print("[red]  No tokens returned from screener — check your API key.[/red]")
        tokens = []

    console.print(f"   Found {len(tokens)} tokens to analyse.")
    console.print()

    # ── Step 2 — SM netflow (primary chain) ──────────────────────────────────
    console.print(f"[bold]2.[/bold] Fetching Smart Money netflow on {chain_upper}…")
    if mock:
        netflow_raw = _mock_netflow()
        _mock_call(f"research smart-money netflow --chain {chain}", 0.38)
    else:
        netflow_raw = nansen(
            ["research", "smart-money", "netflow", "--chain", chain, "--timeframe", "24h"],
            label=f"SM netflow ({chain})")

    netflow_rows = extract_rows(netflow_raw)
    # Build lookup: token_address → 24h netflow USD
    # Real API: net_flow_24h_usd  |  mock: netflow_usd
    netflow_map: dict[str, float] = {}
    for row in netflow_rows:
        addr = screener_field(row, "token_address", "address", default="")
        nf   = screener_field(row, "net_flow_24h_usd", "netflow_usd", "net_flow_usd", default=0)
        netflow_map[addr] = float(nf)

    # Real API: net_flow_24h_usd (positive = inflow, negative = outflow)
    # Fallback for mock: inflow_usd / outflow_usd
    total_sm_net = sum(
        float(screener_field(r, "net_flow_24h_usd", "netflow_usd", "inflow_usd", default=0)) -
        float(screener_field(r, "_outflow_placeholder", "outflow_usd", default=0))
        for r in netflow_rows
    )
    market_posture = "RISK-ON 🟢" if total_sm_net >= 0 else "RISK-OFF 🔴"
    console.print(f"   Overall SM posture → [bold]{market_posture}[/bold]  "
                  f"(SM net flow {fmt_usd(total_sm_net)})")
    console.print()

    # ── Step 3 — SM DEX trades ────────────────────────────────────────────────
    console.print(f"[bold]3.[/bold] Fetching Smart Money DEX trades on {chain_upper}…")
    if mock:
        dex_raw = _mock_dex_trades()
        _mock_call(f"research smart-money dex-trades --chain {chain} --labels Fund", 0.51)
    else:
        dex_raw = nansen(
            ["research", "smart-money", "dex-trades", "--chain", chain,
             "--labels", "Fund", "--limit", "50", "--timeframe", "24h"],
            label=f"SM DEX trades — Fund label ({chain})")

    dex_trades = extract_rows(dex_raw)
    # Count fund trades per token
    fund_trade_count: dict[str, int] = {}
    fund_trade_vol: dict[str, float] = {}
    for trade in dex_trades:
        addr = screener_field(
            trade, "token_bought_address", "token_address", "token_contract_address",
            "bought_token_address", default="")
        fund_trade_count[addr] = fund_trade_count.get(addr, 0) + 1
        vol = screener_field(trade, "amount_usd", "value_usd", "usd_amount", default=0)
        fund_trade_vol[addr] = fund_trade_vol.get(addr, 0) + float(vol)

    console.print(f"   {len(dex_trades)} fund trades captured.")
    console.print()

    # ── Step 4 — SM holdings ─────────────────────────────────────────────────
    console.print(f"[bold]4.[/bold] Fetching Smart Money holdings on {chain_upper}…")
    if mock:
        holdings_raw = _mock_holdings()
        _mock_call(f"research smart-money holdings --chain {chain}", 0.33)
    else:
        holdings_raw = nansen(
            ["research", "smart-money", "holdings", "--chain", chain, "--limit", "30"],
            label=f"SM holdings ({chain})")

    holdings_rows = extract_rows(holdings_raw)
    holdings_rank_map: dict[str, int] = {
        (r.get("token_address") or ""): i + 1
        for i, r in enumerate(holdings_rows)
    }
    console.print(f"   {len(holdings_rows)} tokens in SM portfolio.")
    console.print()

    # ── Step 5-7 — Per-token deep-dive ───────────────────────────────────────
    token_results: list[dict] = []

    for idx, tok in enumerate(tokens):
        # Real screener uses "token_symbol"; mock uses "symbol"
        sym  = screener_field(tok, "token_symbol", "symbol", default="???")
        addr = screener_field(tok, "token_address", "address", default="")
        name = screener_field(tok, "token_name", "name", default=sym)

        console.print(Rule(f"Token {idx+1}/{len(tokens)} — [cyan]{sym}[/cyan] ({name})", style="dim"))

        # 5. Who bought/sold
        console.print(f"   5a. Who-bought-sold…")
        if mock:
            wb_raw = _mock_who_bought(sym)
            _mock_call(f"research token who-bought-sold --chain {chain} --token {addr[:8]}…", 0.45)
        else:
            wb_raw = nansen(
                ["research", "token", "who-bought-sold", "--chain", chain,
                 "--token", addr, "--timeframe", "24h"],
                label=f"who-bought-sold: {sym}")

        # 6. Token indicators
        console.print(f"   5b. Token indicators…")
        if mock:
            ind_raw = _mock_indicators(sym)
            _mock_call(f"research token indicators --chain {chain} --token {addr[:8]}…", 0.29)
        else:
            ind_raw = nansen(
                ["research", "token", "indicators", "--chain", chain, "--token", addr],
                label=f"token indicators: {sym}")

        # 7. Flow intelligence
        console.print(f"   5c. Flow intelligence…")
        if mock:
            fl_raw = _mock_flows(sym)
            _mock_call(f"research token flow-intelligence --chain {chain} --token {addr[:8]}…", 0.55)
        else:
            fl_raw = nansen(
                ["research", "token", "flow-intelligence", "--chain", chain,
                 "--token", addr, "--days", "1"],
                label=f"flow-intelligence: {sym}")

        # Score
        # Real screener uses "netflow" (USD); mock uses "smart_money_netflow_24h_usd"
        # SM netflow for this token (real: net_flow_24h_usd; screener: "netflow")
        tok_netflow = screener_field(tok, "netflow", "net_flow_24h_usd",
                                     "smart_money_netflow_24h_usd", default=0)
        sm_n = netflow_map.get(addr, float(tok_netflow))
        hr   = holdings_rank_map.get(addr, 0)

        # price_change: screener uses "price_change" (already %) or "price_change_24h_pct"
        price_chg = float(screener_field(tok, "price_change_24h_pct", "price_change", default=0))

        score, breakdown = conviction_score(wb_raw, ind_raw, fl_raw, sm_n, 0, hr, price_chg)
        label, colour    = score_to_label(score)

        # who-bought-sold: real API returns list of individual wallets in data.data
        wb_rows = extract_rows(wb_raw)
        # Labeled wallets = Nansen-identified entities (smart money proxies); unlabeled = retail
        sm_buy_vol     = sum(float(r.get("bought_volume_usd", 0)) for r in wb_rows if r.get("address_label"))
        retail_buy_vol = sum(float(r.get("bought_volume_usd", 0)) for r in wb_rows if not r.get("address_label"))
        # Only include labeled buyers in top_buyers — unlabeled wallets carry no signal
        top_buyers = [{"address": r.get("address",""), "label": r.get("address_label",""),
                       "volume_usd": float(r.get("bought_volume_usd", 0))}
                      for r in wb_rows if r.get("address_label")][:3]
        has_smart_buyer = len(top_buyers) > 0

        # flow-intelligence parsed segment flows
        fi = _parse_flow_intelligence(fl_raw)
        fresh_wallet_flow = float(fi.get("fresh_wallets_net_flow_usd", 0))

        # volume: screener uses "volume" or "volume_24h_usd"
        raw_vol = float(screener_field(tok, "volume_24h_usd", "volume", default=0))

        token_results.append({
            "symbol": sym,
            "name": name,
            "address": addr,
            "price_usd": float(screener_field(tok, "price_usd", default=0)),
            "price_change_24h": price_chg,
            "volume_24h_usd": raw_vol,
            "sm_netflow_usd": sm_n,
            "sm_trader_flow": float(fi.get("smart_trader_net_flow_usd", 0)),
            "top_pnl_flow": float(fi.get("top_pnl_net_flow_usd", 0)),
            "whale_flow": float(fi.get("whale_net_flow_usd", 0)),
            "fresh_wallet_flow": fresh_wallet_flow,
            "sm_buy_vol": sm_buy_vol,
            "retail_buy_vol": retail_buy_vol,
            "has_smart_buyer": has_smart_buyer,
            "holdings_rank": hr,
            "score": score,
            "breakdown": breakdown,
            "signal": label,
            "colour": colour,
            "top_buyers": top_buyers,
        })
        console.print(f"   → Conviction score: [{colour}]{score:.0f}/100  {label}[/{colour}]")
        console.print()

    # ── Step 8 — Profile top smart-tagged buyer wallet ───────────────────────
    # Only profile wallets Nansen has labeled — unlabeled wallets carry no signal.
    # If no smart-tagged buyer exists across any token, flag as low conviction.
    top_buyer_addr  = None
    top_buyer_label = None
    top_buyer_token = None
    for tr in sorted(token_results, key=lambda x: -x["score"]):
        for buyer in tr["top_buyers"]:  # already filtered to labeled-only
            a = buyer.get("address", "")
            if a:
                top_buyer_addr  = a
                top_buyer_label = buyer.get("label", "")
                top_buyer_token = tr["symbol"]
                break
        if top_buyer_addr:
            break

    if not top_buyer_addr:
        console.print(f"[bold]8.[/bold] [yellow]No Nansen-labeled buyers found across scanned tokens "
                      f"— Low Conviction flag set.[/yellow]")
        console.print()

    if top_buyer_addr:
        console.print(f"[bold]8.[/bold] Profiling top wallet: [cyan]{top_buyer_addr[:12]}…[/cyan]")
        if mock:
            wallet_raw = _mock_wallet_profile(top_buyer_addr)
            _mock_call(f"research profiler balance --address {top_buyer_addr[:8]}…", 0.41)
        else:
            wallet_raw = nansen(
                ["research", "profiler", "balance", "--address", top_buyer_addr, "--chain", chain],
                label=f"wallet profile: {top_buyer_addr[:8]}…")

        # profiler balance returns a list of token holdings in data.data
        holdings_list = extract_rows(wallet_raw)
        if isinstance(holdings_list, dict):
            holdings_list = []
        total_pv = sum(float(h.get("value_usd", h.get("balance_usd", 0))) for h in holdings_list)
        top3 = sorted(holdings_list, key=lambda h: float(h.get("value_usd", 0)), reverse=True)[:3]
        top3_str = ", ".join(
            f"{h.get('token_symbol','?')} ({fmt_usd(float(h.get('value_usd',0)))})"
            for h in top3
        ) or "—"
        short_addr = f"{top_buyer_addr[:6]}…{top_buyer_addr[-4:]}"
        label_str  = f"[bold]{top_buyer_label}[/bold]" if top_buyer_label else "[dim]unlabeled[/dim]"
        console.print(f"   Entity : {label_str}  (top buyer of [cyan]{top_buyer_token}[/cyan])")
        console.print(f"   Address: [cyan]{short_addr}[/cyan]  |  "
                      f"Portfolio: [green]{fmt_usd(total_pv)}[/green]")
        console.print(f"   Top holdings: {top3_str}")
        console.print()

    # ── Step 9 — Cross-chain comparison ───────────────────────────────────────
    alt_chain = "ethereum" if chain == "solana" else "solana"
    console.print(f"[bold]9.[/bold] Cross-chain SM netflow ({alt_chain.upper()} for comparison)…")
    if mock:
        alt_nf = _mock_eth_netflow()
        _mock_call(f"research smart-money netflow --chain {alt_chain}", 0.36)
    else:
        alt_nf = nansen(
            ["research", "smart-money", "netflow", "--chain", alt_chain, "--timeframe", "24h"],
            label=f"SM netflow ({alt_chain}) — cross-chain")

    alt_rows = extract_rows(alt_nf)
    alt_net = sum(
        float(screener_field(r, "net_flow_24h_usd", "netflow_usd", "inflow_usd", default=0)) -
        float(screener_field(r, "_ph", "outflow_usd", default=0))
        for r in alt_rows
    )
    alt_posture = "RISK-ON 🟢" if alt_net >= 0 else "RISK-OFF 🔴"
    console.print(f"   {alt_chain.upper()} posture → [bold]{alt_posture}[/bold]  "
                  f"(SM net flow {fmt_usd(alt_net)})")
    console.print()

    # ── Step 10 — AI synthesis ────────────────────────────────────────────────
    console.print(f"[bold]10.[/bold] Generating AI analysis…")
    summary_payload = {
        "chain": chain,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "market_posture": market_posture,
        "cross_chain": {"chain": alt_chain, "posture": alt_posture, "net_flow_usd": alt_net},
        "total_sm_net_flow_usd": total_sm_net,
        "tokens": [
            {k: v for k, v in tr.items() if k not in ("colour", "top_buyers")}
            for tr in token_results
        ]
    }

    if skip_ai:
        ai_text = "_AI synthesis disabled (--no-ai)_"
    else:
        ai_text = ai_synthesis(chain, summary_payload)

    # ── Final display ─────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold cyan]── RESULTS ──[/bold cyan]", style="cyan"))
    console.print()

    # Market overview panel
    nf_col = "green" if total_sm_net >= 0 else "red"
    overview = (
        f"  Chain        : [bold]{chain_upper}[/bold]\n"
        f"  SM Posture   : [bold]{market_posture}[/bold]  vs  {alt_chain.upper()} [{alt_posture}]\n"
        f"  SM Net Flow  : [{nf_col}]{fmt_usd(total_sm_net)}[/{nf_col}] (24h)\n"
        f"  Fund Trades  : {len(dex_trades)} captured in 24h"
    )
    console.print(Panel(overview, title="Market Overview", border_style="cyan", padding=(0, 2)))
    console.print()

    # Token signals table
    tbl = Table(title=f"Token Conviction Scores — {chain_upper}",
                box=box.ROUNDED, show_lines=True, header_style="bold magenta")
    tbl.add_column("Rank", justify="center", width=5)
    tbl.add_column("Token",        min_width=8)
    tbl.add_column("Price",        justify="right")
    tbl.add_column("24h %",        justify="right")
    tbl.add_column("SM Netflow",   justify="right")
    tbl.add_column("SM Trader Flow", justify="right")
    tbl.add_column("SM Rank",      justify="center", width=8)
    tbl.add_column("Score",        justify="center", width=7)
    tbl.add_column("Signal",       justify="center", min_width=13, no_wrap=True)

    for rank, tr in enumerate(sorted(token_results, key=lambda x: -x["score"]), 1):
        chg_str = fmt_pct(tr["price_change_24h"])
        chg_col = "green" if tr["price_change_24h"] >= 0 else "red"
        nf_col  = "green" if tr["sm_netflow_usd"]   >= 0 else "red"
        sf_col  = "green" if tr["sm_trader_flow"]   >= 0 else "red"
        hr_str  = f"#{tr['holdings_rank']}" if tr["holdings_rank"] else "—"

        tbl.add_row(
            str(rank),
            f"[bold]{tr['symbol']}[/bold]",
            f"${tr['price_usd']:.6f}" if tr["price_usd"] < 0.01 else
            f"${tr['price_usd']:.4f}" if tr["price_usd"] < 1 else f"${tr['price_usd']:.2f}",
            f"[{chg_col}]{chg_str}[/{chg_col}]",
            f"[{nf_col}]{fmt_usd(tr['sm_netflow_usd'])}[/{nf_col}]",
            f"[{sf_col}]{fmt_usd(tr['sm_trader_flow'])}[/{sf_col}]",
            hr_str,
            f"[{tr['colour']}]{tr['score']:.0f}[/{tr['colour']}]",
            f"[{tr['colour']}]{tr['signal']}[/{tr['colour']}]",
        )
    console.print(tbl)
    console.print()

    # Score breakdown detail + insider signal flag
    FACTOR_MAX = {"sm_segment_flow": 35, "indicator_score": 25,
                  "price_momentum": 15, "holdings_rank": 15, "netflow_momentum": 10}
    for tr in sorted(token_results, key=lambda x: -x["score"]):
        bd = tr["breakdown"]
        console.print(f"[bold]{tr['symbol']}[/bold] score breakdown:")
        for factor, val in bd.items():
            max_val = FACTOR_MAX.get(factor, 10)
            pct     = val / max_val * 100 if max_val else 0
            bar     = _bar(pct)
            console.print(f"  {factor:<20} [{bar}] {val:.1f}/{max_val}")

        # Fresh wallet insider signal — when both smart_trader and fresh_wallet flows are
        # positive simultaneously, it may indicate coordinated insider accumulation.
        fw = tr.get("fresh_wallet_flow", 0)
        st = tr.get("sm_trader_flow", 0)
        if fw > 0 and st > 0:
            console.print(f"  [bold yellow]⚡ Insider Signal:[/bold yellow] "
                          f"fresh_wallet ({fmt_usd(fw)}) + smart_trader ({fmt_usd(st)}) "
                          f"both positive — possible coordinated accumulation")
        elif not tr.get("has_smart_buyer"):
            console.print(f"  [yellow]⚠ Low Conviction: no Nansen-labeled buyers in who-bought-sold[/yellow]")
        console.print()

    # AI panel
    if not skip_ai and "ANTHROPIC_API_KEY" in os.environ:
        console.print(Panel(ai_text, title="[bold yellow]Claude AI Analysis[/bold yellow]",
                            border_style="yellow", padding=(1, 2)))
        console.print()

    # API call log
    _print_api_log()

    # ── Save output ───────────────────────────────────────────────────────────
    if output:
        _save_markdown(output, chain, market_posture, alt_chain, alt_posture,
                       total_sm_net, token_results, ai_text, len(dex_trades))
        console.print(f"[green]Report saved → {output}[/green]")


# ──────────────────────────────────────────────────────────────────────────────
# Markdown report
# ──────────────────────────────────────────────────────────────────────────────

def _save_markdown(path, chain, posture, alt_chain, alt_posture, sm_net, tokens, ai_text, trade_count):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Nansen Smart Money Signal Report — {chain.upper()}",
        f"_Generated {ts}_",
        "",
        "## Market Overview",
        f"| Chain | Posture | SM Net Flow (24h) |",
        f"|-------|---------|------------------|",
        f"| {chain.upper()} | {posture} | {fmt_usd(sm_net)} |",
        f"| {alt_chain.upper()} | {alt_posture} | — |",
        "",
        f"Fund-labelled DEX trades captured: **{trade_count}**",
        "",
        "## Token Signals",
        "",
        "| Rank | Token | Price | 24h% | SM Netflow | Score | Signal |",
        "|------|-------|-------|------|------------|-------|--------|",
    ]
    for rank, tr in enumerate(sorted(tokens, key=lambda x: -x["score"]), 1):
        lines.append(
            f"| {rank} | **{tr['symbol']}** | ${tr['price_usd']:.6f} | "
            f"{tr['price_change_24h']:+.1f}% | {fmt_usd(tr['sm_netflow_usd'])} | "
            f"**{tr['score']:.0f}** | **{tr['signal']}** |"
        )

    lines += [
        "",
        "## Score Breakdown",
        "",
        "| Token | SM Segment Flow | Indicator Score | Price Momentum | Holdings Rank | Netflow Mom. | Total |",
        "|-------|----------------|-----------------|----------------|---------------|--------------|-------|",
    ]
    for tr in sorted(tokens, key=lambda x: -x["score"]):
        bd = tr["breakdown"]
        lines.append(
            f"| {tr['symbol']} | {bd.get('sm_segment_flow',0):.1f}/35 | {bd.get('indicator_score',0):.1f}/25 | "
            f"{bd.get('price_momentum',0):.1f}/15 | {bd.get('holdings_rank',0):.1f}/15 | "
            f"{bd.get('netflow_momentum',0):.1f}/10 | **{tr['score']:.0f}** |"
        )

    lines += ["", "## AI Analysis", "", ai_text, "",
              "---", "_Built with [Nansen CLI](https://agents.nansen.ai) + Claude AI_",
              f"_API calls made: {len(API_CALL_LOG)}_"]

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nansen Smart Money Signal Engine — find where funds are moving before the market.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--chain",   default="solana",
                        choices=["solana","ethereum","base","bnb","arbitrum",
                                 "polygon","optimism","avalanche"],
                        help="Primary chain to scan (default: solana)")
    parser.add_argument("--tokens",  type=int, default=3, metavar="N",
                        help="Number of top tokens to deep-dive (default: 3)")
    parser.add_argument("--mock",    action="store_true",
                        help="Use synthetic data — no API key required")
    parser.add_argument("--no-ai",   action="store_true",
                        help="Skip Claude AI synthesis")
    parser.add_argument("--output",  default="nansen_report.md",
                        help="Save markdown report to this file (default: nansen_report.md)")
    args = parser.parse_args()

    run_pipeline(
        chain    = args.chain,
        top_n    = args.tokens,
        mock     = args.mock,
        skip_ai  = args.no_ai,
        output   = args.output,
    )


if __name__ == "__main__":
    main()
