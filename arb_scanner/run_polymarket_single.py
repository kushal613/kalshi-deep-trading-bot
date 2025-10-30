#!/usr/bin/env python3
"""
Polymarket Single-Venue Arbitrage Scanner

A CLI tool for detecting arbitrage opportunities in Polymarket prediction markets.
Scans all active markets and identifies opportunities where Yes + No ≠ 1.
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.append(str(Path(__file__).parent.parent))

from config import load_config
try:
    from .polymarket_market_fetcher import PolymarketMarketFetcher
    from .polymarket_arbitrage_calculator import PolymarketArbitrageCalculator
    from .polymarket_output_manager import PolymarketOutputManager
except ImportError:
    from polymarket_market_fetcher import PolymarketMarketFetcher
    from polymarket_arbitrage_calculator import PolymarketArbitrageCalculator
    from polymarket_output_manager import PolymarketOutputManager

# Simple Polymarket config class
class PolymarketConfig:
    def __init__(self):
        self.base_url = "https://gamma-api.polymarket.com"
        self.use_mainnet = True

from loguru import logger


async def main():
    """Main function to run the Polymarket arbitrage scanner."""
    parser = argparse.ArgumentParser(
        description="Polymarket Single-Venue Arbitrage Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_polymarket_single.py                    # Run with default settings
  python run_polymarket_single.py --max-opportunities 10  # Show top 10 opportunities
  python run_polymarket_single.py --position-size 50      # Use $50 position size
  python run_polymarket_single.py --fees 0.005            # Set 0.5% fees
  python run_polymarket_single.py --gas 0.01              # Set 1% gas costs

Configuration:
  The scanner uses your existing .env file configuration for Polymarket API access.
  No additional API keys are required for basic market data fetching.
        """
    )
    
    parser.add_argument(
        "--max-opportunities",
        type=int,
        default=20,
        help="Maximum number of opportunities to display (default: 20)"
    )
    
    parser.add_argument(
        "--position-size",
        type=float,
        default=100.0,
        help="Position size in USD for calculations (default: 100.0)"
    )
    
    parser.add_argument(
        "--fees",
        type=float,
        default=0.01,
        help="Trading fees as decimal (default: 0.01 = 1%)"
    )
    
    parser.add_argument(
        "--gas",
        type=float,
        default=0.02,
        help="Gas costs as decimal (default: 0.02 = 2%)"
    )
    
    parser.add_argument(
        "--output-file",
        type=str,
        help="Custom output CSV filename (default: auto-generated with timestamp)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
    
    try:
        # Load configuration
        config = load_config()
        polymarket_config = PolymarketConfig()
        
        print("🔍 Polymarket Single-Venue Arbitrage Scanner")
        print("=" * 50)
        print(f"Position size: ${args.position_size}")
        print(f"Fees: {args.fees:.1%}")
        print(f"Gas costs: {args.gas:.1%}")
        print(f"Min edge threshold: {(args.fees + args.gas):.1%}")
        print()
        
        # Initialize components
        calculator = PolymarketArbitrageCalculator(
            position_size=args.position_size,
            fees=args.fees,
            gas=args.gas
        )
        output_manager = PolymarketOutputManager()
        
        # Fetch markets
        print("📡 Fetching Polymarket markets...")
        async with PolymarketMarketFetcher(polymarket_config) as fetcher:
            markets = await fetcher.fetch_markets_direct()
        
        print(f"Found {len(markets)} active markets")
        
        if not markets:
            print("❌ No markets found. Exiting.")
            return
        
        # Calculate opportunities
        print("🧮 Calculating arbitrage opportunities...")
        opportunities = calculator.calculate_opportunities(markets)
        
        if not opportunities:
            print("❌ No arbitrage opportunities found above the minimum threshold.")
            return
        
        # Display opportunities
        print(f"\n✅ Found {len(opportunities)} arbitrage opportunities!")
        output_manager.display_opportunities(opportunities, max_display=args.max_opportunities)
        
        # Save to CSV
        csv_file = output_manager.save_to_csv(opportunities, args.output_file)
        if csv_file:
            print(f"\n💾 Results saved to: {csv_file}")
        
        print("\n🎯 Scanner completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Scanner interrupted by user")
    except Exception as e:
        logger.error(f"Scanner error: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
