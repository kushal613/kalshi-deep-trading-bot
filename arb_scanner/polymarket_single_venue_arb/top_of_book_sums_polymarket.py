#!/usr/bin/env python3
"""
Collect top-of-book quotes across active Polymarket binary markets and plot distributions.

Outputs:
- CSV snapshot with yes_bid/no_bid/yes_ask/no_ask and sums
- Two PNGs: ask_sum and bid_sum histograms with stats tables

Usage:
    python top_of_book_sums_polymarket.py --output-dir outputs --verbose
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from loguru import logger

try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False

sys.path.append(str(Path(__file__).parent.parent))
from config import load_config

try:
    from .polymarket_market_fetcher import PolymarketMarketFetcher
except ImportError:
    from polymarket_market_fetcher import PolymarketMarketFetcher


def _is_binary_with_quotes(m: Dict[str, Any]) -> bool:
    try:
        yb = float(m.get("yes_bid", 0) or 0)
        nb = float(m.get("no_bid", 0) or 0)
        ya = float(m.get("yes_ask", 0) or 0)
        na = float(m.get("no_ask", 0) or 0)
        return (0 < yb < 1 and 0 < nb < 1 and 0 < ya < 1 and 0 < na < 1)
    except Exception:
        return False


def _compute_sums(m: Dict[str, Any]) -> Dict[str, Any]:
    yb = float(m.get("yes_bid", 0))
    nb = float(m.get("no_bid", 0))
    ya = float(m.get("yes_ask", 0))
    na = float(m.get("no_ask", 0))
    return {
        "yes_bid": yb,
        "no_bid": nb,
        "yes_ask": ya,
        "no_ask": na,
        "ask_sum": ya + na,
        "bid_sum": yb + nb,
    }


async def _fetch_active_markets(config) -> List[Dict[str, Any]]:
    from types import SimpleNamespace
    # Polymarket fetcher uses absolute URLs; base_url can be empty
    poly_cfg = SimpleNamespace(base_url="")
    async with PolymarketMarketFetcher(poly_cfg) as fetcher:
        markets = await fetcher.fetch_markets_direct()
        if not markets:
            return []
        return [m for m in markets if _is_binary_with_quotes(m)]


def _save_csv(rows: List[Dict[str, Any]], output_dir: Path) -> str:
    import csv
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"polymarket_top_of_book_sums_{ts}.csv"
    fields = [
        "timestamp",
        "market_id",
        "question",
        "category",
        "yes_bid",
        "no_bid",
        "yes_ask",
        "no_ask",
        "ask_sum",
        "bid_sum",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    logger.info(f"Saved Polymarket snapshot CSV: {path}")
    return str(path)


def _format_stats(values: List[float]) -> Dict[str, str]:
    import numpy as np
    if not values:
        return {k: "-" for k in ["count","mean","median","std","min","p5","p25","p75","p95","max"]}
    arr = np.array(values, dtype=float)
    return {
        "count": f"{arr.size}",
        "mean": f"{arr.mean():.4f}",
        "median": f"{np.median(arr):.4f}",
        "std": f"{(arr.std(ddof=1) if arr.size>1 else 0):.4f}",
        "min": f"{arr.min():.4f}",
        "p5": f"{np.percentile(arr,5):.4f}",
        "p25": f"{np.percentile(arr,25):.4f}",
        "p75": f"{np.percentile(arr,75):.4f}",
        "p95": f"{np.percentile(arr,95):.4f}",
        "max": f"{arr.max():.4f}",
    }


def _plot_distributions(rows: List[Dict[str, Any]], output_dir: Path) -> List[str]:
    if not HAS_MPL:
        logger.warning("matplotlib not installed; skipping plots")
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ask_vals = [r["ask_sum"] for r in rows]
    bid_vals = [r["bid_sum"] for r in rows]
    ask_stats = _format_stats(ask_vals)
    bid_stats = _format_stats(bid_vals)
    paths: List[str] = []

    # ask plot + stats
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(8, 7), gridspec_kw={"height_ratios":[3,1]})
    axh, axt = axes
    axh.hist(ask_vals, bins=40, color="#4C78A8", alpha=0.85)
    axh.set_title("Polymarket: Distribution of ask_sum (yes_ask + no_ask)")
    axh.set_xlabel("ask_sum (probability)")
    axh.set_ylabel("count")
    axt.axis('off')
    table = axt.table(cellText=[[k,v] for k,v in ask_stats.items()], colLabels=["stat","value"], loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1,1.3)
    ask_path = output_dir / f"polymarket_ask_sum_hist_{ts}.png"
    fig.tight_layout()
    fig.savefig(ask_path, dpi=150)
    plt.close(fig)
    paths.append(str(ask_path))

    # bid plot + stats
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(8, 7), gridspec_kw={"height_ratios":[3,1]})
    axh, axt = axes
    axh.hist(bid_vals, bins=40, color="#F58518", alpha=0.85)
    axh.set_title("Polymarket: Distribution of bid_sum (yes_bid + no_bid)")
    axh.set_xlabel("bid_sum (probability)")
    axh.set_ylabel("count")
    axt.axis('off')
    table = axt.table(cellText=[[k,v] for k,v in bid_stats.items()], colLabels=["stat","value"], loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1,1.3)
    bid_path = output_dir / f"polymarket_bid_sum_hist_{ts}.png"
    fig.tight_layout()
    fig.savefig(bid_path, dpi=150)
    plt.close(fig)
    paths.append(str(bid_path))
    logger.info(f"Saved Polymarket plots: {paths}")
    return paths


async def main() -> int:
    parser = argparse.ArgumentParser(description="Polymarket top-of-book sums",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    parser.add_argument("--output-dir", type=str, default="outputs", help="Directory to save CSV/PNGs")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.remove(); logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove(); logger.add(sys.stderr, level="INFO")

    output_dir = Path(args.output_dir)

    logger.info("Loading configuration...")
    config = load_config()

    logger.info("Fetching Polymarket active markets...")
    markets = await _fetch_active_markets(config)
    if not markets:
        logger.error("No Polymarket markets with quotes found")
        return 1
    logger.info(f"Active binary markets: {len(markets)}")

    timestamp = datetime.utcnow().isoformat() + "Z"
    rows: List[Dict[str, Any]] = []
    for m in markets:
        sums = _compute_sums(m)
        rows.append({
            "timestamp": timestamp,
            "market_id": m.get("market_id", ""),
            "question": m.get("question", ""),
            "category": m.get("category", ""),
            **sums,
        })

    csv_path = _save_csv(rows, output_dir)
    _plot_distributions(rows, output_dir)
    logger.info("Completed Polymarket top-of-book snapshot.")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


