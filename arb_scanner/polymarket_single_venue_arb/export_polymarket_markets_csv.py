#!/usr/bin/env python3
"""
Export Polymarket active binary markets to CSV.

Writes columns: market_id, title, yes_price, no_price, end_date, volume, liquidity
"""
import asyncio
import csv
from pathlib import Path
from typing import Any, Dict, List

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))
# Use polymarket-specific config to get base_url
try:
    from polymarket.config import load_config as load_polymarket_config
except Exception:
    sys.path.append(str(Path(__file__).resolve().parents[2] / 'polymarket'))
    from config import load_config as load_polymarket_config
from loguru import logger

try:
    from .polymarket_market_fetcher import PolymarketMarketFetcher
except Exception:
    from arb_scanner.polymarket_single_venue_arb.polymarket_market_fetcher import PolymarketMarketFetcher


async def export(output: Path = None) -> Path:
    cfg = load_polymarket_config()
    out_path = output or Path(__file__).parent / "outputs" / "polymarket_markets.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with PolymarketMarketFetcher(cfg.polymarket) as pmf:
        markets = await pmf.fetch_markets_direct()

    if not markets:
        raise RuntimeError("No Polymarket markets available to export")

    rows: List[Dict[str, Any]] = []
    for m in markets:
        title = m.get("question") or m.get("title") or ""
        rows.append({
            "market_id": m.get("market_id") or m.get("id") or "",
            "title": title,
            "yes_price": float(m.get("yes_price", 0) or 0),
            "no_price": float(m.get("no_price", 0) or 0),
            "end_date": m.get("end_date") or "",
            "volume": float(m.get("volume", 0) or 0),
            "liquidity": float(m.get("liquidity", 0) or 0),
        })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "market_id",
                "title",
                "yes_price",
                "no_price",
                "end_date",
                "volume",
                "liquidity",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    logger.info(f"Exported {len(rows)} Polymarket markets to {out_path}")
    return out_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Polymarket markets to CSV")
    parser.add_argument("--output", default="", help="Output CSV path; default writes to outputs/polymarket_markets.csv")
    args = parser.parse_args()
    output = Path(args.output) if args.output else None
    asyncio.run(export(output=output))


if __name__ == "__main__":
    main()


