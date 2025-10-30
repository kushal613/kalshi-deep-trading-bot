# Polymarket Single-Venue Arbitrage Scanner

A CLI tool for detecting arbitrage opportunities in Polymarket prediction markets. This scanner identifies markets where Yes + No ≠ 1, indicating potential arbitrage opportunities.

## Features

- **Complete Market Coverage**: Fetches all active Polymarket markets using their official Gamma API
- **Real-time Price Data**: Gets current Yes/No prices for each market
- **Arbitrage Detection**: Identifies markets where Yes + No ≠ 1
- **Financial Calculations**: Computes edge, ROI, capital requirements, and profit potential
- **Risk Filtering**: Filters out opportunities below minimum threshold (fees + gas)
- **CSV Export**: Saves results to timestamped CSV files
- **Console Display**: Shows formatted table of opportunities sorted by ROI

## Installation

The scanner uses the existing project dependencies. No additional installation required.

## Usage

### Basic Usage

```bash
python3 run_polymarket_single.py
```

### Advanced Options

```bash
python3 run_polymarket_single.py --max-opportunities 10 --position-size 50 --fees 0.005 --gas 0.01 --verbose
```

### Command Line Arguments

- `--max-opportunities N`: Maximum number of opportunities to display (default: 20)
- `--position-size AMOUNT`: Position size in USD for calculations (default: 100.0)
- `--fees RATE`: Trading fees as decimal (default: 0.01 = 1%)
- `--gas RATE`: Gas costs as decimal (default: 0.02 = 2%)
- `--output-file FILENAME`: Custom output CSV filename
- `--verbose`: Enable verbose logging

## How It Works

### 1. Market Fetching
- Connects to Polymarket's Gamma API
- Fetches all active markets with pagination
- Extracts Yes/No prices and market metadata
- Filters out expired or inactive markets

### 2. Arbitrage Detection
- Calculates total price = Yes price + No price
- Computes edge = 1 - total price
- Classifies opportunities:
  - `buy_both`: Yes + No < 1 (under-round)
  - `sell_both`: Yes + No > 1 (over-round)

### 3. Financial Analysis
- **Edge**: Absolute difference from 1.0
- **ROI %**: (edge / total_cost) × 100
- **Annualized ROI %**: roi × (365 / days_to_expiry)
- **Capital Required**: (Yes + No) × position_size
- **Profit**: abs(edge) × position_size

### 4. Risk Filtering
- Filters out opportunities where abs(edge) < fees + gas
- Ensures only profitable opportunities are reported

## Output

### Console Display
Shows a formatted table with:
- Market ID and question
- Opportunity type (buy_both/sell_both)
- Total price and edge
- Capital required and potential profit
- ROI percentage and days to expiry
- Liquidity score

### CSV Export
Saves detailed results to `outputs/polymarket_opportunities_YYYYMMDD_HHMMSS.csv` with columns:
- Market metadata (ID, question, description, end_date)
- Price data (yes_bid, no_bid, yes_ask, no_ask, yes_price, no_price)
- Financial metrics (total_price, edge, opportunity_type, capital_required, profit)
- Performance metrics (roi_percent, annualized_roi_percent)
- Risk metrics (min_spread, liquidity_score, volume, liquidity)

## Example Output

```
🔍 Polymarket Single-Venue Arbitrage Scanner
==================================================
Position size: $100.0
Fees: 1.0%
Gas costs: 2.0%
Min edge threshold: 3.0%

📡 Fetching Polymarket markets...
Found 3578 active markets
🧮 Calculating arbitrage opportunities...

❌ No arbitrage opportunities found above the minimum threshold.
```

## Technical Details

### API Integration
- Uses Polymarket's official Gamma API (no authentication required)
- Implements pagination to fetch all markets
- Handles multiple API endpoints for reliability
- Includes GraphQL fallback via The Graph Protocol

### Price Handling
- Polymarket uses 0-1 decimal range (not cents like Kalshi)
- Prices are already in the correct format for calculations
- No conversion needed between API and calculations

### Error Handling
- Graceful handling of API failures
- Continues processing if individual markets fail
- Comprehensive logging for debugging

## Configuration

The scanner uses a simple configuration class with default values:
- Base URL: `https://gamma-api.polymarket.com`
- Use mainnet: `True`
- No API keys required for basic market data

## Dependencies

- `httpx`: HTTP client for API requests
- `loguru`: Logging
- `tabulate`: Optional for enhanced table display
- `csv`: CSV file handling
- `asyncio`: Asynchronous operations

## Files

- `run_polymarket_single.py`: Main CLI script
- `polymarket_market_fetcher.py`: Market data fetching
- `polymarket_arbitrage_calculator.py`: Arbitrage calculations
- `polymarket_output_manager.py`: Output formatting and CSV export

## Notes

- The scanner found 0 arbitrage opportunities in 3,578 markets, indicating efficient pricing
- This is expected behavior for mature prediction markets
- The scanner correctly identifies when markets are efficiently priced
- Results are saved to CSV even when no opportunities are found (empty file)
