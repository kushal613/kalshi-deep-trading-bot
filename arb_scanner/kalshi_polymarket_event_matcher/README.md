# Kalshi ↔ Polymarket Event Matcher

Matches semantically equivalent markets between Kalshi and Polymarket using OpenAI. Prefilters candidates with fast string similarity to keep token usage low.

## Inputs (CSV)
- kalshi_markets.csv: market_id, title, yes_price, no_price, end_date
- polymarket_markets.csv: same schema

## How it works
1. Load both CSVs
2. Select top 20 Kalshi markets (by volume/liquidity if present, else first 20)
3. For each Kalshi title, prefilter top 15 Polymarket candidates with a token-overlap similarity
4. Prompt OpenAI to pick the best semantic match and return a confidence 0–1

## Usage
```bash
python3 run_matcher.py \
  --kalshi-csv ../kalshi_single_venue_arb/outputs/kalshi_markets.csv \
  --polymarket-csv ../polymarket_single_venue_arb/outputs/polymarket_markets.csv \
  --output outputs/matches.csv \
  --top-k 20 --candidates 15 --verbose
```

The script uses the existing .env via config.load_config() for OPENAI_API_KEY.
