# Polymarket Deep Trading Bot

A decentralized prediction market trading bot that uses AI-powered research and sophisticated risk management to identify and execute trades on Polymarket.

## Overview

This bot follows the same architecture as the Kalshi Deep Trading Bot but adapts it for Polymarket's decentralized ecosystem:

**Data → AI Signal → Trade**

1. **Fetch Markets**: Gets top Polymarket markets sorted by volume and liquidity
2. **Research Markets**: Uses Octagon Deep Research AI to analyze each market
3. **Extract Probabilities**: Converts research into structured probability estimates
4. **Make Decisions**: Uses OpenAI to generate betting decisions based on research vs market prices
5. **Execute Trades**: Places trades on Polymarket (simulation or live)

## Key Features

### AI-Powered Analysis
- **Octagon Deep Research**: Market analysis and probability predictions
- **OpenAI GPT-4**: Structured betting decision making
- **Automatic Probability Extraction**: Converts research text to structured data

### Sophisticated Risk Management
- **R-score Filtering**: Only bets on statistically significant opportunities (z-score ≥ 1.5)
- **Kelly Criterion**: Optimal position sizing based on edge and risk
- **Portfolio Limits**: Maximum number of simultaneous positions
- **Hedging**: Automatic hedge positions for risk management

### Safety Features
- **Dry Run Mode**: Test strategies without placing real bets
- **Simulation Mode**: Works without API keys or private keys
- **Liquidity Filtering**: Only trades markets with sufficient liquidity
- **Confidence Thresholds**: Only bets on high-confidence opportunities

## Quick Start

### 1. Install Dependencies

```bash
cd polymarket
pip install -r requirements.txt
```

### 2. Set Up Environment

```bash
cp env_template.txt .env
# Edit .env with your API keys
```

Required API keys:
- **Octagon API**: Get from [app.octagonai.co](https://app.octagonai.co)
- **OpenAI API**: Get from [platform.openai.com](https://platform.openai.com/api-keys)

Optional (for enhanced functionality):
- **Polymarket API**: Get from [polymarket.com](https://polymarket.com)
- **Private Key**: Your wallet private key for live trading

### 3. Run the Bot

**Dry Run Mode (Default):**
```bash
python main.py
```

**Live Trading Mode:**
```bash
python main.py --live
```

## Configuration

Key settings in `.env`:

```env
# Market Analysis
MAX_MARKETS_TO_ANALYZE=50      # Number of top markets to analyze
MINIMUM_LIQUIDITY=1000.0       # Minimum liquidity required
MAX_BET_AMOUNT=100.0           # Maximum bet per market

# Risk Management
Z_THRESHOLD=1.5                # Minimum R-score for betting
ENABLE_KELLY_SIZING=true       # Use Kelly criterion for position sizing
KELLY_FRACTION=0.5             # Fraction of Kelly to use
BANKROLL=1000.0                # Total bankroll for calculations

# Hedging
ENABLE_HEDGING=true            # Enable automatic hedging
HEDGE_RATIO=0.25               # Hedge ratio (25% of main bet)
```

## Architecture

### Core Components

- `main.py`: Main bot orchestration and workflow
- `data.py`: Polymarket data fetching using polymarket-apis
- `trade.py`: Trading execution and position management
- `config.py`: Configuration management

### Data Flow

1. **Market Discovery**: Fetches active Polymarket markets via API
2. **Research Phase**: Uses Octagon AI to analyze each market
3. **Probability Extraction**: Converts research to structured probabilities
4. **Decision Making**: OpenAI generates betting decisions
5. **Risk Filtering**: Applies R-score and Kelly criteria
6. **Trade Execution**: Places orders on Polymarket

## Trading Strategy

The bot uses **hedge-fund style risk management**:

- **Statistical Edge**: Only bets when R-score ≥ 1.5 (market mispriced by ≥1.5 standard deviations)
- **Kelly Sizing**: Position sizes based on optimal Kelly criterion
- **Selective Betting**: Skips most markets, focuses on exceptional opportunities
- **Risk Hedging**: Automatically creates hedge positions for lower-confidence bets

## Polymarket Integration

### Data Sources
- **Polymarket Gamma API**: Market data and pricing
- **polymarket-apis**: Official Python client library
- **Web3 Integration**: Direct blockchain interaction for live trading

### Trading Modes
- **Simulation Mode**: Works without API keys or private keys
- **Dry Run Mode**: Shows decisions without placing real trades
- **Live Trading**: Actually places trades on Polymarket

## Safety & Risk Management

**Important Disclaimers**

- **Educational/Research Only**: This software is for educational purposes
- **No Financial Advice**: All decisions are automated algorithms
- **Risk of Loss**: Trading involves significant financial risk
- **Use at Your Own Risk**: You are solely responsible for trading decisions

### Built-in Safety Features

- **Dry Run by Default**: No real trades unless explicitly enabled
- **Liquidity Requirements**: Only trades liquid markets
- **Position Limits**: Maximum bet amounts and portfolio limits
- **Confidence Thresholds**: Only bets on high-confidence opportunities

## Development

### Testing Flow

1. **Dry Run**: Test with simulation mode
2. **Small Scale**: Test with few markets
3. **Live Trading**: Test with real money (small amounts)

### Error Handling

The bot handles various scenarios:
- API rate limits and timeouts
- Market data inconsistencies
- Network connectivity issues
- Insufficient liquidity

## Differences from Kalshi Bot

| Feature | Kalshi Bot | Polymarket Bot |
|---------|------------|----------------|
| **Platform** | Centralized API | Decentralized blockchain |
| **Authentication** | RSA signatures | Web3 wallet signatures |
| **Data Source** | Kalshi API | Polymarket Gamma API |
| **Trading** | Centralized orders | Decentralized smart contracts |
| **Settlement** | Centralized | Blockchain-based |

## Limitations

- **Market Coverage**: Limited to Polymarket's available markets
- **Research Quality**: Depends on Octagon Deep Research data quality
- **Decision Making**: Relies on OpenAI's analysis capabilities
- **Gas Costs**: Live trading incurs blockchain transaction fees

## Support

For issues or questions:
1. Check the error logs for detailed error messages
2. Verify API credentials and network connectivity
3. Test with smaller market limits first
4. Use dry run mode for debugging

## License

This project is for educational and research purposes. Use at your own risk.
