#!/usr/bin/env python3
"""
Export Kalshi active binary markets to CSV with volume fields.

Writes columns: market_id, title, yes_price, no_price, end_date, volume_24h, volume, liquidity

Selection:
- If possible, fetch server-side sorted markets. Otherwise, fetch all open markets and sort client-side by volume_24h then volume.
"""
import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))
from config import KalshiConfig, load_config
from loguru import logger

try:
    from .market_fetcher import MarketFetcher
except Exception:
    # Fallback when running as a script
    from arb_scanner.kalshi_single_venue_arb.market_fetcher import MarketFetcher


def _normalize_price(value: Any) -> float:
    try:
        p = float(value)
    except Exception:
        return 0.0
    # Kalshi API often returns cents (0..100). Normalize to 0..1 when needed.
    if p > 1.0:
        p = p / 100.0
    if p < 0:
        return 0.0
    return min(1.0, p)


def _mid_price(bid: Any, ask: Any) -> float:
    bid_n = _normalize_price(bid)
    ask_n = _normalize_price(ask)
    if bid_n > 0 and ask_n > 0 and ask_n >= bid_n:
        return (bid_n + ask_n) / 2.0
    # Fallback to whichever side is present
    return bid_n or ask_n or 0.0


async def export(top_k: int = 100, output: Path = None) -> Path:
    cfg = load_config()
    kalshi_cfg: KalshiConfig = cfg.kalshi
    out_path = output or Path(__file__).parent / "outputs" / "kalshi_markets.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with MarketFetcher(kalshi_cfg) as mf:
        # Prefer direct markets fetch to get market-level volume fields
        markets = await mf.fetch_markets_direct()
        if not markets:
            logger.warning("No markets returned; falling back to fetch_all_active_markets")
            markets = await mf.fetch_all_active_markets()

    if not markets:
        raise RuntimeError("No Kalshi markets available to export")

    # Filter binary-like markets and compute fields
    processed: List[Dict[str, Any]] = []
    for m in markets:
        title = m.get("title") or m.get("name") or ""
        ticker = m.get("ticker") or m.get("market_ticker") or ""
        close_time = m.get("close_time") or m.get("end_date") or ""
        yes_bid = m.get("yes_bid")
        yes_ask = m.get("yes_ask")
        no_bid = m.get("no_bid")
        no_ask = m.get("no_ask")

        # Derive mid prices with normalization (handles 0..100 cents)
        yes_price = _mid_price(yes_bid, yes_ask)
        no_price = _mid_price(no_bid, no_ask)

        processed.append({
            "market_id": ticker,
            "title": title,
            "yes_price": yes_price,
            "no_price": no_price,
            "end_date": close_time,
            "volume_24h": float(m.get("volume_24h", 0) or 0),
            "volume": float(m.get("volume", 0) or 0),
            "liquidity": float(m.get("liquidity", 0) or 0),
        })

    # De-dup by title, keep first
    seen = set()
    deduped = []
    for pm in processed:
        t = (pm.get("title") or "").strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        deduped.append(pm)

    # Sort: volume_24h desc, then volume, then liquidity
    deduped.sort(key=lambda x: (x.get("volume_24h", 0), x.get("volume", 0), x.get("liquidity", 0)), reverse=True)

    top = deduped[:top_k] if top_k and top_k > 0 else deduped

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "market_id",
                "title",
                "yes_price",
                "no_price",
                "end_date",
                "volume_24h",
                "volume",
                "liquidity",
            ],
        )
        writer.writeheader()
        for row in top:
            writer.writerow(row)
    logger.info(f"Exported {len(top)} Kalshi markets to {out_path}")
    return out_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Kalshi markets with volume columns to CSV")
    parser.add_argument("--top-k", type=int, default=100, help="Top markets by 24h volume to export")
    parser.add_argument("--output", default="", help="Output CSV path; default writes to outputs/kalshi_markets.csv")
    args = parser.parse_args()
    output = Path(args.output) if args.output else None
    asyncio.run(export(top_k=args.top_k, output=output))


if __name__ == "__main__":
    main()


