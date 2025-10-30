"""
Polymarket output manager for saving and displaying arbitrage opportunities.
"""
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import List
from loguru import logger

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    from .polymarket_arbitrage_calculator import PolymarketArbitrageOpportunity
except ImportError:
    from polymarket_arbitrage_calculator import PolymarketArbitrageOpportunity


class PolymarketOutputManager:
    """Manages output of Polymarket arbitrage opportunities."""
    
    def __init__(self, output_dir: str = "outputs"):
        """
        Initialize the output manager.
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def save_to_csv(self, opportunities: List[PolymarketArbitrageOpportunity], 
                   filename: str = None) -> str:
        """
        Save arbitrage opportunities to CSV file.
        
        Args:
            opportunities: List of arbitrage opportunities
            filename: Optional custom filename
            
        Returns:
            Path to the saved CSV file
        """
        if not opportunities:
            logger.warning("No opportunities to save")
            return ""
        
        # Generate filename with timestamp
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"polymarket_opportunities_{timestamp}.csv"
        
        filepath = self.output_dir / filename
        
        # Write CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'market_id', 'question', 'description', 'end_date', 'days_to_expiry',
                'yes_bid', 'no_bid', 'yes_ask', 'no_ask', 'yes_price', 'no_price',
                'total_price', 'edge', 'opportunity_type', 'capital_required', 'profit',
                'roi_percent', 'annualized_roi_percent', 'min_spread', 'liquidity_score',
                'volume', 'liquidity'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for opp in opportunities:
                writer.writerow({
                    'market_id': opp.market_id,
                    'question': opp.question,
                    'description': opp.description,
                    'end_date': opp.end_date,
                    'days_to_expiry': opp.days_to_expiry,
                    'yes_bid': opp.yes_bid,
                    'no_bid': opp.no_bid,
                    'yes_ask': opp.yes_ask,
                    'no_ask': opp.no_ask,
                    'yes_price': opp.yes_price,
                    'no_price': opp.no_price,
                    'total_price': opp.total_price,
                    'edge': opp.edge,
                    'opportunity_type': opp.opportunity_type,
                    'capital_required': opp.capital_required,
                    'profit': opp.profit,
                    'roi_percent': opp.roi_percent,
                    'annualized_roi_percent': opp.annualized_roi_percent,
                    'min_spread': opp.min_spread,
                    'liquidity_score': opp.liquidity_score,
                    'volume': opp.volume,
                    'liquidity': opp.liquidity
                })
        
        logger.info(f"Saved {len(opportunities)} opportunities to {filepath}")
        return str(filepath)
    
    def display_opportunities(self, opportunities: List[PolymarketArbitrageOpportunity], 
                            max_display: int = 20):
        """
        Display arbitrage opportunities in a formatted table.
        
        Args:
            opportunities: List of arbitrage opportunities
            max_display: Maximum number of opportunities to display
        """
        if not opportunities:
            print("No arbitrage opportunities found.")
            return
        
        # Limit display
        display_opps = opportunities[:max_display]
        
        if HAS_TABULATE:
            self._display_tabulated_table(display_opps)
        else:
            self._display_simple_table(display_opps)
        
        # Show summary
        total_opportunities = len(opportunities)
        total_capital = sum(opp.capital_required for opp in opportunities)
        total_profit = sum(opp.profit for opp in opportunities)
        avg_roi = sum(opp.roi_percent for opp in opportunities) / total_opportunities if total_opportunities > 0 else 0
        
        print(f"\n📊 Summary:")
        print(f"   Total opportunities: {total_opportunities}")
        print(f"   Total capital required: ${total_capital:,.2f}")
        print(f"   Total potential profit: ${total_profit:,.2f}")
        print(f"   Average ROI: {avg_roi:.2f}%")
        
        if total_opportunities > max_display:
            print(f"   (Showing top {max_display} opportunities)")
    
    def _display_tabulated_table(self, opportunities: List[PolymarketArbitrageOpportunity]):
        """Display opportunities using tabulate library."""
        headers = [
            "Market ID", "Question", "Type", "Total Price", "Edge", 
            "Capital", "Profit", "ROI %", "Days", "Liquidity"
        ]
        
        rows = []
        for opp in opportunities:
            rows.append([
                opp.market_id[:20] + "..." if len(opp.market_id) > 20 else opp.market_id,
                opp.question[:30] + "..." if len(opp.question) > 30 else opp.question,
                opp.opportunity_type,
                f"{opp.total_price:.4f}",
                f"{opp.edge:.4f}",
                f"${opp.capital_required:.2f}",
                f"${opp.profit:.2f}",
                f"{opp.roi_percent:.2f}%",
                f"{opp.days_to_expiry}d",
                f"{opp.liquidity_score:.2f}"
            ])
        
        print(tabulate(rows, headers=headers, tablefmt="grid"))
    
    def _display_simple_table(self, opportunities: List[PolymarketArbitrageOpportunity]):
        """Display opportunities in a simple table format."""
        print("\n" + "="*120)
        print(f"{'Market ID':<20} {'Question':<30} {'Type':<10} {'Total Price':<12} {'Edge':<8} {'Capital':<10} {'Profit':<10} {'ROI %':<8} {'Days':<6} {'Liquidity':<10}")
        print("="*120)
        
        for opp in opportunities:
            market_id = opp.market_id[:18] + ".." if len(opp.market_id) > 20 else opp.market_id
            question = opp.question[:28] + ".." if len(opp.question) > 30 else opp.question
            
            print(f"{market_id:<20} {question:<30} {opp.opportunity_type:<10} "
                  f"{opp.total_price:<12.4f} {opp.edge:<8.4f} ${opp.capital_required:<9.2f} "
                  f"${opp.profit:<9.2f} {opp.roi_percent:<7.2f}% {opp.days_to_expiry:<5}d "
                  f"{opp.liquidity_score:<9.2f}")
        
        print("="*120)
