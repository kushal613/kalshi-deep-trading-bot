#!/usr/bin/env python3
"""
Collect top-of-book quotes across active Kalshi markets and plot distributions.

This script:
- Fetches all active markets using the existing MarketFetcher (which pulls yes/no top-of-book fields)
- Computes ask_sum (yes_ask + no_ask) and bid_sum (yes_bid + no_bid)
- Persists a CSV snapshot
- Generates two plots (histograms) for ask_sum and bid_sum as PNGs

Usage:
    python top_of_book_sums.py --output-dir outputs --verbose
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from loguru import logger

# Optional plotting dependencies
try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False

# Add parent directory to path to import config and fetcher
sys.path.append(str(Path(__file__).parent.parent))
from config import load_config

try:
    from .market_fetcher import MarketFetcher
except ImportError:
    from market_fetcher import MarketFetcher


def _is_binary_market(m: Dict[str, Any]) -> bool:
    """Heuristic: a tradable YES/NO market has all four top-of-book fields.
    Accept numeric strings; prices are in cents per Kalshi API.
    """
    try:
        yes_bid = float(m.get("yes_bid", 0) or 0)
        no_bid = float(m.get("no_bid", 0) or 0)
        yes_ask = float(m.get("yes_ask", 0) or 0)
        no_ask = float(m.get("no_ask", 0) or 0)
        return (yes_bid > 0 and no_bid > 0 and yes_ask > 0 and no_ask > 0)
    except Exception:
        return False


def _compute_sums_cents(m: Dict[str, Any]) -> Dict[str, Any]:
    """Compute ask_sum and bid_sum in cents, plus decimal versions for convenience."""
    yes_bid = float(m.get("yes_bid", 0))
    no_bid = float(m.get("no_bid", 0))
    yes_ask = float(m.get("yes_ask", 0))
    no_ask = float(m.get("no_ask", 0))

    ask_sum_c = yes_ask + no_ask
    bid_sum_c = yes_bid + no_bid

    return {
        "yes_bid_cents": yes_bid,
        "no_bid_cents": no_bid,
        "yes_ask_cents": yes_ask,
        "no_ask_cents": no_ask,
        "ask_sum_cents": ask_sum_c,
        "bid_sum_cents": bid_sum_c,
        "yes_bid": yes_bid / 100.0,
        "no_bid": no_bid / 100.0,
        "yes_ask": yes_ask / 100.0,
        "no_ask": no_ask / 100.0,
        "ask_sum": ask_sum_c / 100.0,
        "bid_sum": bid_sum_c / 100.0,
    }


async def _fetch_active_markets(config, top_n: int = 0) -> List[Dict[str, Any]]:
    """Fetch active markets with top-of-book fields.
    If top_n > 0, pull top events by volume and fetch odds per market ticker,
    limiting to roughly top_n markets to reduce API load.
    """
    async with MarketFetcher(config.kalshi) as fetcher:
        if top_n and top_n > 0:
            # Fetch top events by volume using events endpoint
            events = await fetcher.client.get_events(limit=top_n)
            tickers: List[Dict[str, Any]] = []
            for ev in events:
                for m in ev.get("markets", []) or []:
                    if m.get("ticker"):
                        tickers.append({
                            "ticker": m.get("ticker"),
                            "title": m.get("title", ""),
                            "event_ticker": ev.get("event_ticker", ""),
                            "category": ev.get("category", ""),
                            "volume": m.get("volume", 0)
                        })
            # Take top_n by market volume
            tickers.sort(key=lambda x: x.get("volume", 0), reverse=True)
            tickers = tickers[:top_n]
            # Fetch odds for each ticker
            results: List[Dict[str, Any]] = []
            for t in tickers:
                detailed = await fetcher.client.get_market_with_odds(t["ticker"])
                if detailed:
                    detailed.update({
                        "title": t.get("title", detailed.get("title", "")),
                        "event_ticker": t.get("event_ticker", ""),
                        "category": t.get("category", "")
                    })
                    results.append(detailed)
            return [m for m in results if _is_binary_market(m)]
        else:
            # Full markets scan (pagination)
            markets = await fetcher.fetch_markets_direct()
            if not markets:
                return []
            return [m for m in markets if _is_binary_market(m)]


def _save_csv(rows: List[Dict[str, Any]], output_dir: Path) -> str:
    import csv

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"top_of_book_sums_{ts}.csv"
    path = output_dir / filename

    fieldnames = [
        "timestamp",
        "ticker",
        "title",
        "event_ticker",
        "category",
        "yes_bid_cents",
        "no_bid_cents",
        "yes_ask_cents",
        "no_ask_cents",
        "ask_sum_cents",
        "bid_sum_cents",
        "yes_bid",
        "no_bid",
        "yes_ask",
        "no_ask",
        "ask_sum",
        "bid_sum",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    logger.info(f"Saved snapshot CSV: {path}")
    return str(path)


def _format_stats(values: List[float]) -> Dict[str, str]:
    import numpy as np
    if not values:
        return {
            "count": "0",
            "mean": "-",
            "median": "-",
            "std": "-",
            "min": "-",
            "p5": "-",
            "p25": "-",
            "p75": "-",
            "p95": "-",
            "max": "-",
        }
    arr = np.array(values, dtype=float)
    return {
        "count": f"{arr.size}",
        "mean": f"{arr.mean():.4f}",
        "median": f"{np.median(arr):.4f}",
        "std": f"{arr.std(ddof=1):.4f}" if arr.size > 1 else "0.0000",
        "min": f"{arr.min():.4f}",
        "p5": f"{np.percentile(arr, 5):.4f}",
        "p25": f"{np.percentile(arr, 25):.4f}",
        "p75": f"{np.percentile(arr, 75):.4f}",
        "p95": f"{np.percentile(arr, 95):.4f}",
        "max": f"{arr.max():.4f}",
    }


def _plot_distributions(rows: List[Dict[str, Any]], output_dir: Path) -> List[str]:
    if not HAS_MPL:
        logger.warning("matplotlib not installed; skipping plot generation.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    ask_vals = [r["ask_sum"] for r in rows]
    bid_vals = [r["bid_sum"] for r in rows]
    ask_stats = _format_stats(ask_vals)
    bid_stats = _format_stats(bid_vals)

    paths = []

    # Ask sum histogram + stats table
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(8, 7), gridspec_kw={"height_ratios": [3, 1]})
    ax_hist, ax_table = axes
    ax_hist.hist(ask_vals, bins=40, color="#4C78A8", alpha=0.85)
    ax_hist.set_title("Distribution of ask_sum (yes_ask + no_ask)")
    ax_hist.set_xlabel("ask_sum (dollars)")
    ax_hist.set_ylabel("count")
    ax_table.axis('off')
    table_data = [[k, v] for k, v in ask_stats.items()]
    table = ax_table.table(cellText=table_data, colLabels=["stat", "value"], loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.3)
    ask_path = output_dir / f"ask_sum_hist_{ts}.png"
    fig.tight_layout()
    fig.savefig(ask_path, dpi=150)
    plt.close(fig)
    paths.append(str(ask_path))

    # Bid sum histogram + stats table
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(8, 7), gridspec_kw={"height_ratios": [3, 1]})
    ax_hist, ax_table = axes
    ax_hist.hist(bid_vals, bins=40, color="#F58518", alpha=0.85)
    ax_hist.set_title("Distribution of bid_sum (yes_bid + no_bid)")
    ax_hist.set_xlabel("bid_sum (dollars)")
    ax_hist.set_ylabel("count")
    ax_table.axis('off')
    table_data = [[k, v] for k, v in bid_stats.items()]
    table = ax_table.table(cellText=table_data, colLabels=["stat", "value"], loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.3)
    bid_path = output_dir / f"bid_sum_hist_{ts}.png"
    fig.tight_layout()
    fig.savefig(bid_path, dpi=150)
    plt.close(fig)
    paths.append(str(bid_path))

    logger.info(f"Saved plots: {paths}")
    return paths


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect top-of-book sums across active Kalshi markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Directory to save CSV and PNG files (default: outputs)"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=0,
        help="If > 0, fetch roughly top-N active markets by volume via events and per-ticker odds"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    output_dir = Path(args.output_dir)

    # Load config for authenticated client headers (MarketFetcher handles auth/signing)
    logger.info("Loading configuration...")
    config = load_config()

    # Fetch active markets and filter
    logger.info("Fetching active markets...")
    markets = await _fetch_active_markets(config, top_n=args.top_n)
    if not markets:
        logger.error("No active markets with top-of-book data found.")
        return 1
    logger.info(f"Active binary markets: {len(markets)}")

    # Build snapshot rows
    timestamp = datetime.utcnow().isoformat() + "Z"
    rows: List[Dict[str, Any]] = []
    for m in markets:
        sums = _compute_sums_cents(m)
        rows.append({
            "timestamp": timestamp,
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "event_ticker": m.get("event_ticker", ""),
            "category": m.get("category", ""),
            **sums,
        })

    # Save CSV
    csv_path = _save_csv(rows, output_dir)

    # Generate plots (PNG)
    _plot_distributions(rows, output_dir)

    logger.info("Completed top-of-book sums snapshot.")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


