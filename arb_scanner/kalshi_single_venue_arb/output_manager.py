"""
Output management for arbitrage scanner results.
Handles CSV export and console display.
"""

import csv
import os
from typing import List
from datetime import datetime
from pathlib import Path
from loguru import logger
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    from .arbitrage_calculator import ArbitrageOpportunity
except ImportError:
    from arbitrage_calculator import ArbitrageOpportunity


class OutputManager:
    """Manages output of arbitrage opportunities to CSV and console."""
    
    def __init__(self, output_dir: str = "outputs"):
        """
        Initialize the output manager.
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def save_to_csv(self, opportunities: List[ArbitrageOpportunity], filename: str = None) -> str:
        """
        Save opportunities to CSV file.
        
        Args:
            opportunities: List of ArbitrageOpportunity objects
            filename: Optional custom filename
            
        Returns:
            Path to the saved CSV file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"kalshi_opportunities_{timestamp}.csv"
        
        filepath = self.output_dir / filename
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'ticker', 'title', 'event_ticker', 'event_title', 'category',
                    'close_time', 'strike_date', 'days_to_expiry',
                    'yes_bid', 'no_bid', 'yes_ask', 'no_ask',
                    'yes_price', 'no_price', 'total_price', 'edge',
                    'opportunity_type', 'capital_required', 'profit',
                    'roi_percent', 'annualized_roi_percent',
                    'min_spread', 'liquidity_score'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for opp in opportunities:
                    writer.writerow({
                        'ticker': opp.ticker,
                        'title': opp.title,
                        'event_ticker': opp.event_ticker,
                        'event_title': opp.event_title,
                        'category': opp.category,
                        'close_time': opp.close_time,
                        'strike_date': opp.strike_date,
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
                        'liquidity_score': opp.liquidity_score
                    })
            
            logger.info(f"Saved {len(opportunities)} opportunities to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving CSV file: {e}")
            raise
    
    def display_console_table(self, opportunities: List[ArbitrageOpportunity], max_rows: int = 20):
        """
        Display opportunities in a formatted console table.
        
        Args:
            opportunities: List of ArbitrageOpportunity objects
            max_rows: Maximum number of rows to display
        """
        if not opportunities:
            print("No arbitrage opportunities found.")
            return
        
        # Limit the number of rows displayed
        display_opportunities = opportunities[:max_rows]
        
        # Prepare table data
        table_data = []
        for opp in display_opportunities:
            table_data.append([
                opp.ticker[:12] + "..." if len(opp.ticker) > 15 else opp.ticker,
                opp.opportunity_type,
                f"{opp.total_price:.4f}",
                f"{opp.edge:.4f}",
                f"${opp.capital_required:.2f}",
                f"${opp.profit:.2f}",
                f"{opp.roi_percent:.2f}%",
                f"{opp.annualized_roi_percent:.2f}%",
                f"{opp.days_to_expiry}d",
                f"{opp.liquidity_score:.1f}"
            ])
        
        # Create table headers
        headers = [
            "Ticker",
            "Type",
            "Total Price",
            "Edge",
            "Capital",
            "Profit",
            "ROI %",
            "Annual ROI %",
            "Days",
            "Liquidity"
        ]
        
        # Display the table
        print("\n" + "="*120)
        print("KALSHI ARBITRAGE OPPORTUNITIES")
        print("="*120)
        
        if HAS_TABULATE:
            print(tabulate(table_data, headers=headers, tablefmt="grid", stralign="right"))
        else:
            # Fallback simple table display
            self._display_simple_table(table_data, headers)
        
        if len(opportunities) > max_rows:
            print(f"\n... and {len(opportunities) - max_rows} more opportunities")
        
        # Display summary statistics
        self._display_summary_stats(opportunities)
    
    def _display_summary_stats(self, opportunities: List[ArbitrageOpportunity]):
        """Display summary statistics."""
        if not opportunities:
            return
        
        buy_both_count = sum(1 for opp in opportunities if opp.opportunity_type == "buy_both")
        sell_both_count = sum(1 for opp in opportunities if opp.opportunity_type == "sell_both")
        
        total_capital = sum(opp.capital_required for opp in opportunities)
        total_profit = sum(opp.profit for opp in opportunities)
        avg_roi = sum(opp.roi_percent for opp in opportunities) / len(opportunities)
        avg_annual_roi = sum(opp.annualized_roi_percent for opp in opportunities) / len(opportunities)
        
        print(f"\nSUMMARY STATISTICS:")
        print(f"Total Opportunities: {len(opportunities)}")
        print(f"Buy Both: {buy_both_count} | Sell Both: {sell_both_count}")
        print(f"Total Capital Required: ${total_capital:,.2f}")
        print(f"Total Potential Profit: ${total_profit:,.2f}")
        print(f"Average ROI: {avg_roi:.2f}%")
        print(f"Average Annualized ROI: {avg_annual_roi:.2f}%")
        print("="*120)
    
    def _display_simple_table(self, table_data, headers):
        """Simple table display without tabulate dependency."""
        # Calculate column widths
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(header)
            for row in table_data:
                max_width = max(max_width, len(str(row[i])))
            col_widths.append(max_width + 2)
        
        # Print header
        header_line = "|"
        separator_line = "|"
        for i, header in enumerate(headers):
            header_line += f" {header:<{col_widths[i]-1}}|"
            separator_line += "-" * col_widths[i] + "|"
        
        print(header_line)
        print(separator_line)
        
        # Print data rows
        for row in table_data:
            data_line = "|"
            for i, cell in enumerate(row):
                data_line += f" {str(cell):<{col_widths[i]-1}}|"
            print(data_line)
