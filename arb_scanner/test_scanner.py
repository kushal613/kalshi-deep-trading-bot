#!/usr/bin/env python3
"""
Test script for the arbitrage scanner.
Tests the core functionality without requiring API credentials.
"""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from arbitrage_calculator import ArbitrageCalculator, ArbitrageOpportunity

def test_arbitrage_calculator():
    """Test the arbitrage calculator with mock data."""
    print("Testing ArbitrageCalculator...")
    
    # Create calculator
    calculator = ArbitrageCalculator(position_size=100.0, fees=0.02, gas=0.01)
    
    # Mock market data
    mock_markets = [
        {
            "ticker": "TEST-MARKET-1",
            "title": "Test Market 1",
            "event_ticker": "TEST-EVENT-1",
            "event_title": "Test Event 1",
            "category": "Politics",
            "close_time": "2024-12-31T23:59:59Z",
            "strike_date": "2024-12-31T23:59:59Z",
            "yes_bid": 0.45,
            "no_bid": 0.50,
            "yes_ask": 0.47,
            "no_ask": 0.52,
            "volume": 1000,
            "status": "open"
        },
        {
            "ticker": "TEST-MARKET-2", 
            "title": "Test Market 2",
            "event_ticker": "TEST-EVENT-2",
            "event_title": "Test Event 2",
            "category": "Economics",
            "close_time": "2024-11-30T23:59:59Z",
            "strike_date": "2024-11-30T23:59:59Z",
            "yes_bid": 0.55,
            "no_bid": 0.48,
            "yes_ask": 0.57,
            "no_ask": 0.50,
            "volume": 2000,
            "status": "open"
        },
        {
            "ticker": "TEST-MARKET-3",
            "title": "Test Market 3", 
            "event_ticker": "TEST-EVENT-3",
            "event_title": "Test Event 3",
            "category": "Sports",
            "close_time": "2024-10-31T23:59:59Z",
            "strike_date": "2024-10-31T23:59:59Z",
            "yes_bid": 0.49,
            "no_bid": 0.49,
            "yes_ask": 0.51,
            "no_ask": 0.51,
            "volume": 500,
            "status": "open"
        }
    ]
    
    # Calculate opportunities
    opportunities = calculator.calculate_opportunities(mock_markets)
    
    print(f"Found {len(opportunities)} opportunities:")
    for opp in opportunities:
        print(f"  {opp.ticker}: {opp.opportunity_type} - Edge: {opp.edge:.4f}, ROI: {opp.roi_percent:.2f}%")
    
    # Test specific calculations
    if opportunities:
        opp = opportunities[0]
        print(f"\nDetailed analysis for {opp.ticker}:")
        print(f"  Yes Price: {opp.yes_price:.4f}")
        print(f"  No Price: {opp.no_price:.4f}")
        print(f"  Total Price: {opp.total_price:.4f}")
        print(f"  Edge: {opp.edge:.4f}")
        print(f"  Capital Required: ${opp.capital_required:.2f}")
        print(f"  Profit: ${opp.profit:.2f}")
        print(f"  ROI: {opp.roi_percent:.2f}%")
        print(f"  Annualized ROI: {opp.annualized_roi_percent:.2f}%")
        print(f"  Days to Expiry: {opp.days_to_expiry}")
        print(f"  Liquidity Score: {opp.liquidity_score:.1f}")
    
    return len(opportunities) > 0

def test_output_manager():
    """Test the output manager with mock data."""
    print("\nTesting OutputManager...")
    
    from output_manager import OutputManager
    
    # Create output manager
    output_manager = OutputManager(output_dir="test_outputs")
    
    # Create mock opportunities
    mock_opportunities = [
        ArbitrageOpportunity(
            ticker="TEST-1",
            title="Test Market 1",
            event_ticker="EVENT-1",
            event_title="Test Event 1",
            category="Politics",
            close_time="2024-12-31T23:59:59Z",
            strike_date="2024-12-31T23:59:59Z",
            days_to_expiry=30,
            yes_bid=0.45,
            no_bid=0.50,
            yes_ask=0.47,
            no_ask=0.52,
            yes_price=0.46,
            no_price=0.51,
            total_price=0.97,
            edge=0.03,
            opportunity_type="buy_both",
            capital_required=97.0,
            profit=3.0,
            roi_percent=3.09,
            annualized_roi_percent=37.63,
            min_spread=0.02,
            liquidity_score=7.5
        )
    ]
    
    # Test CSV output
    try:
        csv_path = output_manager.save_to_csv(mock_opportunities, "test_opportunities.csv")
        print(f"CSV saved to: {csv_path}")
        
        # Test console display
        output_manager.display_console_table(mock_opportunities)
        
        return True
    except Exception as e:
        print(f"Error testing output manager: {e}")
        return False

def main():
    """Run all tests."""
    print("Running Arbitrage Scanner Tests...")
    print("=" * 50)
    
    success = True
    
    # Test calculator
    if not test_arbitrage_calculator():
        print("❌ ArbitrageCalculator test failed")
        success = False
    else:
        print("✅ ArbitrageCalculator test passed")
    
    # Test output manager
    if not test_output_manager():
        print("❌ OutputManager test failed")
        success = False
    else:
        print("✅ OutputManager test passed")
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
