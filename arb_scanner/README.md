# Kalshi Arbitrage Scanner - Phase 1

Single-venue arbitrage detection for Kalshi markets. This tool identifies opportunities where the sum of Yes and No prices deviates from 1.0, indicating potential arbitrage opportunities.

## Features

- **Market Data Fetching**: Pulls all active Kalshi markets with real-time price data
- **Arbitrage Detection**: Identifies buy_both (under-round) and sell_both (over-round) opportunities
- **Financial Calculations**: Computes edge, ROI, annualized ROI, capital requirements, and profit potential
- **Risk Filtering**: Filters out opportunities below minimum profitability thresholds
- **CSV Export**: Saves results to timestamped CSV files
- **Console Display**: Shows formatted tables with key metrics

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have a valid `.env` file with Kalshi API credentials:
```env
KALSHI_API_KEY=your_api_key_here
KALSHI_PRIVATE_KEY=your_private_key_here
KALSHI_USE_DEMO=true
```

## Usage

### Basic Usage
```bash
python run_single.py
```

### Advanced Options
```bash
python run_single.py \
    --position-size 1000.0 \
    --fees 0.02 \
    --gas 0.01 \
    --max-opportunities 50 \
    --output-dir results \
    --verbose
```

### Command Line Options

- `--position-size SIZE`: Position size for calculations (default: 100.0)
- `--fees FEES`: Trading fees as percentage (default: 0.02 = 2%)
- `--gas GAS`: Gas costs as percentage (default: 0.01 = 1%)
- `--max-opportunities N`: Maximum opportunities to display (default: 20)
- `--output-dir DIR`: Output directory for CSV files (default: outputs)
- `--verbose`: Enable verbose logging
- `--help`: Show help message

## Output

### Console Table
The tool displays a formatted table showing:
- Ticker, Opportunity Type, Total Price, Edge
- Capital Required, Profit, ROI %, Annual ROI %
- Days to Expiry, Liquidity Score

### CSV Export
Results are saved to `outputs/kalshi_opportunities_YYYYMMDD_HHMMSS.csv` with detailed fields for further analysis.

## Arbitrage Logic

### Opportunity Types
- **buy_both**: When Yes + No < 1.0 (under-round)
- **sell_both**: When Yes + No > 1.0 (over-round)

### Key Metrics
- **Edge**: `1.0 - (Yes + No)`
- **ROI %**: `(edge / total_cost) × 100`
- **Annualized ROI %**: `roi × (365 / days_to_expiry)`
- **Capital Required**: `(Yes + No) × position_size`
- **Profit**: `abs(edge) × position_size`

### Filtering
Only opportunities where `abs(edge) >= fees + gas` are included in results.

## Example Output

```
================================================================================
KALSHI ARBITRAGE OPPORTUNITIES
================================================================================
| Ticker        | Type      | Total Price | Edge   | Capital | Profit | ROI % | Annual ROI % | Days | Liquidity |
|---------------|-----------|-------------|--------|---------|--------|-------|--------------|------|-----------|
| TRUMP2024-WIN | buy_both  | 0.9850      | 0.0150 | $98.50  | $1.50  | 1.52% | 15.20%       | 36   | 7.2       |
| BIDEN2024-WIN | sell_both | 1.0120      | -0.0120| $101.20 | $1.20  | 1.19% | 12.10%       | 36   | 6.8       |
```

## Architecture

- `market_fetcher.py`: Handles Kalshi API communication
- `arbitrage_calculator.py`: Core arbitrage detection logic
- `output_manager.py`: CSV export and console display
- `run_single.py`: Main CLI script

## Future Enhancements

- Polymarket integration
- Cross-venue arbitrage detection
- Real-time monitoring
- Advanced risk metrics
- Portfolio optimization

