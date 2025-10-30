#!/usr/bin/env python3
"""
Kalshi Arbitrage Scanner - Phase 1

Single-venue arbitrage detection for Kalshi markets.
Detects opportunities where Yes + No ≠ 1 and calculates potential profits.

Usage:
    python run_single.py [options]

Options:
    --position-size SIZE    Position size for calculations (default: 100.0)
    --fees FEES            Trading fees as percentage (default: 0.02 = 2%)
    --gas GAS              Gas costs as percentage (default: 0.01 = 1%)
    --max-opportunities N  Maximum opportunities to display (default: 20)
    --output-dir DIR        Output directory for CSV files (default: outputs)
    --help                 Show this help message
"""

import asyncio
import argparse
import sys
from pathlib import Path
from loguru import logger

# Add parent directory to path to import config
sys.path.append(str(Path(__file__).parent.parent))

from config import load_config
try:
    from .market_fetcher import MarketFetcher
    from .arbitrage_calculator import ArbitrageCalculator
    from .output_manager import OutputManager
except ImportError:
    from market_fetcher import MarketFetcher
    from arbitrage_calculator import ArbitrageCalculator
    from output_manager import OutputManager


async def main():
    """Main function to run the arbitrage scanner."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Kalshi Arbitrage Scanner - Phase 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--position-size",
        type=float,
        default=100.0,
        help="Position size for calculations (default: 100.0)"
    )
    
    parser.add_argument(
        "--fees",
        type=float,
        default=0.02,
        help="Trading fees as percentage (default: 0.02 = 2%)"
    )
    
    parser.add_argument(
        "--gas",
        type=float,
        default=0.01,
        help="Gas costs as percentage (default: 0.01 = 1%)"
    )
    
    parser.add_argument(
        "--max-opportunities",
        type=int,
        default=20,
        help="Maximum opportunities to display (default: 20)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Output directory for CSV files (default: outputs)"
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
        logger.info("Loading configuration...")
        config = load_config()
        
        # Initialize components
        logger.info("Initializing arbitrage scanner...")
        calculator = ArbitrageCalculator(
            position_size=args.position_size,
            fees=args.fees,
            gas=args.gas
        )
        output_manager = OutputManager(output_dir=args.output_dir)
        
        # Fetch market data
        logger.info("Fetching market data from Kalshi...")
        async with MarketFetcher(config.kalshi) as fetcher:
            markets = await fetcher.fetch_markets_direct()
            
            if not markets:
                logger.error("No markets found. Check your API credentials and connection.")
                return 1
            
            logger.info(f"Found {len(markets)} active markets")
        
        # Calculate arbitrage opportunities
        logger.info("Calculating arbitrage opportunities...")
        opportunities = calculator.calculate_opportunities(markets)
        
        if not opportunities:
            logger.info("No arbitrage opportunities found above the minimum threshold.")
            return 0
        
        # Save to CSV
        logger.info("Saving results to CSV...")
        csv_path = output_manager.save_to_csv(opportunities)
        logger.info(f"Results saved to: {csv_path}")
        
        # Display console table
        logger.info("Displaying results...")
        output_manager.display_console_table(opportunities, max_rows=args.max_opportunities)
        
        logger.info("Arbitrage scan completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Scan interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error during arbitrage scan: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
