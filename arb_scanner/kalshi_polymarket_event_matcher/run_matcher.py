#!/usr/bin/env python3
"""
Kalshi ↔ Polymarket Event Matcher

Matches semantically identical prediction markets between Kalshi and Polymarket using OpenAI.

Inputs (CSV, same schema):
  - market_id, title, yes_price, no_price, end_date

Usage:
  python3 run_matcher.py \
    --kalshi-csv ../kalshi_single_venue_arb/outputs/kalshi_markets.csv \
    --polymarket-csv ../polymarket_single_venue_arb/outputs/polymarket_markets.csv \
    --output outputs/matches.csv \
    --top-k 20 --candidates 15 --verbose
"""
import argparse
import csv
import json
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Ensure project root on sys.path to import config
sys.path.append(str(Path(__file__).resolve().parents[2]))
from config import load_config
from loguru import logger

try:
    import openai
    from openai import AsyncOpenAI
except Exception:
    openai = None
    AsyncOpenAI = None


def load_markets(csv_path: Path) -> List[Dict[str, Any]]:
    markets: List[Dict[str, Any]] = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            markets.append({
                'market_id': row.get('market_id', '').strip(),
                'title': (row.get('title') or '').strip(),
                'yes_price': float(row.get('yes_price') or 0),
                'no_price': float(row.get('no_price') or 0),
                'end_date': (row.get('end_date') or '').strip(),
            })
    return markets


def simple_title_similarity(a: str, b: str) -> float:
    """Compute a quick, dependency-free similarity score between two titles (0-1)."""
    a_norm = ' '.join(a.lower().split())
    b_norm = ' '.join(b.lower().split())
    # Token-set overlap score
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    jaccard = overlap / union if union else 0.0
    # Prefix bonus
    prefix = 1.0 if a_norm[:20] == b_norm[:20] and a_norm[:20] else 0.0
    # Heuristic blend
    return min(1.0, 0.85 * jaccard + 0.15 * prefix)


def pick_top_candidates(kalshi_title: str, polymarkets: List[Dict[str, Any]], max_candidates: int) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for pm in polymarkets:
        score = simple_title_similarity(kalshi_title, pm.get('title', ''))
        scored.append((score, pm))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [pm for _, pm in scored[:max_candidates]]


def select_top_k_kalshi(markets: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    # Deduplicate by title first (keep first occurrence)
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for m in markets:
        t = (m.get('title') or '').strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        deduped.append(m)
    # If the CSV has volume/liquidity columns, sort by them
    key = None
    if deduped and 'volume' in deduped[0]:
        key = 'volume'
    elif deduped and 'liquidity' in deduped[0]:
        key = 'liquidity'
    if key:
        deduped = sorted(deduped, key=lambda m: float(m.get(key, 0) or 0), reverse=True)
    else:
        logger.warning("No volume/liquidity in Kalshi CSV; using input order after de-dup.")
    return deduped[:top_k]


def build_prompt(kalshi: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
    header = (
        "You are matching semantically equivalent prediction markets across venues.\n"
        "Choose the single best Polymarket match for the Kalshi market based on meaning and resolution criteria.\n"
        "Return strict JSON: {\"polymarket_match\": string, \"confidence\": number between 0 and 1}.\n"
    )
    k = f"Kalshi: {kalshi['title']} (end: {kalshi.get('end_date','')})\n"
    lines = [f"Candidates ({len(candidates)}):"]
    for i, c in enumerate(candidates, 1):
        lines.append(f"{i}. {c['title']} (end: {c.get('end_date','')})")
    return header + "\n" + k + "\n" + "\n".join(lines)


async def match_one(client: Any, model: str, kalshi: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Tuple[str, str, float]:
    prompt = build_prompt(kalshi, candidates)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a rigorous, concise market matcher."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=200,
        )
        content = resp.choices[0].message.content or "{}"
        # Best-effort to parse JSON
        match_obj = {}
        try:
            # Extract JSON substring if needed
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                match_obj = json.loads(content[start:end+1])
            else:
                match_obj = json.loads(content)
        except Exception:
            # Fallback: minimal parse
            match_obj = {"polymarket_match": content.strip(), "confidence": 0.5}
        pm_title = str(match_obj.get("polymarket_match", "")).strip()
        conf = float(match_obj.get("confidence", 0.0))
        conf = max(0.0, min(1.0, conf))
        return kalshi['title'], pm_title, conf
    except Exception as e:
        logger.warning(f"LLM match failed for '{kalshi['title']}': {e}")
        return kalshi['title'], "", 0.0


async def run(args):
    cfg = load_config()
    if AsyncOpenAI is None:
        raise RuntimeError("openai package not available in this environment")
    client = AsyncOpenAI(api_key=cfg.openai.api_key)

    kalshi_csv = Path(args.kalshi_csv)
    poly_csv = Path(args.polymarket_csv)
    out_csv = Path(args.output)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    kalshi_markets = load_markets(kalshi_csv)
    poly_markets = load_markets(poly_csv)
    if not kalshi_markets or not poly_markets:
        raise RuntimeError("Empty inputs: ensure both CSVs are populated.")

    top_kalshi = select_top_k_kalshi(kalshi_markets, args.top_k)
    logger.info(f"Selected {len(top_kalshi)} Kalshi markets for matching")

    matches: List[Tuple[str, str, float]] = []
    tasks = []
    for k in top_kalshi:
        candidates = pick_top_candidates(k['title'], poly_markets, args.candidates)
        tasks.append(match_one(client, cfg.openai.model, k, candidates))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            continue
        matches.append(r)

    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["kalshi_title", "polymarket_match", "confidence_score"])
        for row in matches:
            writer.writerow(row)
    logger.info(f"Saved {len(matches)} matches to {out_csv}")


def main():
    parser = argparse.ArgumentParser(description="Kalshi ↔ Polymarket event matcher")
    parser.add_argument("--kalshi-csv", required=True, help="Path to kalshi_markets.csv")
    parser.add_argument("--polymarket-csv", required=True, help="Path to polymarket_markets.csv")
    parser.add_argument("--output", default="outputs/matches.csv", help="Output CSV path")
    parser.add_argument("--top-k", type=int, default=20, help="Num Kalshi markets to match")
    parser.add_argument("--candidates", type=int, default=15, help="Num Polymarket candidates per Kalshi")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Matcher error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


