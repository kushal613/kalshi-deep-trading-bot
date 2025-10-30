"""
Arbitrage opportunity calculator for Kalshi markets.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from loguru import logger


@dataclass
class ArbitrageOpportunity:
    """Represents a single arbitrage opportunity."""
    ticker: str
    title: str
    event_ticker: str
    event_title: str
    category: str
    close_time: str
    strike_date: str
    days_to_expiry: int
    
    # Price data
    yes_bid: float
    no_bid: float
    yes_ask: float
    no_ask: float
    
    # Calculated values
    yes_price: float  # Mid price
    no_price: float   # Mid price
    total_price: float
    edge: float
    opportunity_type: str  # "buy_both" or "sell_both"
    
    # Financial metrics
    capital_required: float
    profit: float
    roi_percent: float
    annualized_roi_percent: float
    
    # Risk metrics
    min_spread: float  # Minimum spread between bid/ask
    liquidity_score: float  # Simple liquidity indicator


class ArbitrageCalculator:
    """Calculates arbitrage opportunities from market data."""
    
    def __init__(self, position_size: float = 100.0, fees: float = 0.02, gas: float = 0.01):
        """
        Initialize the calculator.
        
        Args:
            position_size: Default position size for calculations
            fees: Trading fees as a percentage (2% = 0.02)
            gas: Gas costs as a percentage (1% = 0.01)
        """
        self.position_size = position_size
        self.fees = fees
        self.gas = gas
        self.minimum_edge = fees + gas
    
    def calculate_opportunities(self, markets: List[Dict[str, Any]]) -> List[ArbitrageOpportunity]:
        """
        Calculate arbitrage opportunities from market data.
        
        Args:
            markets: List of market dictionaries with price data
            
        Returns:
            List of ArbitrageOpportunity objects
        """
        opportunities = []
        
        for market in markets:
            try:
                opportunity = self._analyze_market(market)
                if opportunity and abs(opportunity.edge) >= self.minimum_edge:
                    opportunities.append(opportunity)
            except Exception as e:
                logger.warning(f"Error analyzing market {market.get('ticker', 'unknown')}: {e}")
                continue
        
        # Sort by ROI percentage (descending)
        opportunities.sort(key=lambda x: x.annualized_roi_percent, reverse=True)
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        return opportunities
    
    def _analyze_market(self, market: Dict[str, Any]) -> Optional[ArbitrageOpportunity]:
        """
        Analyze a single market for arbitrage opportunities.
        
        Args:
            market: Market dictionary with price data
            
        Returns:
            ArbitrageOpportunity object or None if no opportunity
        """
        # Extract price data
        yes_bid = float(market.get("yes_bid", 0))
        no_bid = float(market.get("no_bid", 0))
        yes_ask = float(market.get("yes_ask", 0))
        no_ask = float(market.get("no_ask", 0))
        
        # Validate price data
        if not all([yes_bid > 0, no_bid > 0, yes_ask > 0, no_ask > 0]):
            return None
        
        # Calculate mid prices (average of bid and ask)
        yes_price = (yes_bid + yes_ask) / 2
        no_price = (no_bid + no_ask) / 2
        total_price = yes_price + no_price
        
        # Calculate edge
        edge = 1.0 - total_price
        
        # Skip if edge is too small
        if abs(edge) < self.minimum_edge:
            return None
        
        # Determine opportunity type
        if total_price < 1.0:
            opportunity_type = "buy_both"
        elif total_price > 1.0:
            opportunity_type = "sell_both"
        else:
            return None  # No arbitrage opportunity
        
        # Calculate financial metrics
        capital_required = total_price * self.position_size
        profit = abs(edge) * self.position_size
        roi_percent = (profit / capital_required) * 100 if capital_required > 0 else 0
        
        # Calculate days to expiry
        days_to_expiry = self._calculate_days_to_expiry(market)
        annualized_roi_percent = roi_percent * (365 / days_to_expiry) if days_to_expiry > 0 else roi_percent
        
        # Calculate risk metrics
        min_spread = min(yes_ask - yes_bid, no_ask - no_bid)
        liquidity_score = self._calculate_liquidity_score(market)
        
        return ArbitrageOpportunity(
            ticker=market.get("ticker", ""),
            title=market.get("title", ""),
            event_ticker=market.get("event_ticker", ""),
            event_title=market.get("event_title", ""),
            category=market.get("category", ""),
            close_time=market.get("close_time", ""),
            strike_date=market.get("strike_date", ""),
            days_to_expiry=days_to_expiry,
            yes_bid=yes_bid,
            no_bid=no_bid,
            yes_ask=yes_ask,
            no_ask=no_ask,
            yes_price=yes_price,
            no_price=no_price,
            total_price=total_price,
            edge=edge,
            opportunity_type=opportunity_type,
            capital_required=capital_required,
            profit=profit,
            roi_percent=roi_percent,
            annualized_roi_percent=annualized_roi_percent,
            min_spread=min_spread,
            liquidity_score=liquidity_score
        )
    
    def _calculate_days_to_expiry(self, market: Dict[str, Any]) -> int:
        """Calculate days until market expiry."""
        try:
            close_time_str = market.get("close_time", "")
            if not close_time_str:
                return 30  # Default fallback
            
            # Parse close time
            if close_time_str.endswith('Z'):
                close_dt = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
            else:
                close_dt = datetime.fromisoformat(close_time_str)
            
            if close_dt.tzinfo is None:
                close_dt = close_dt.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            time_diff = close_dt - now
            days = max(1, int(time_diff.total_seconds() / 86400))  # At least 1 day
            
            return days
            
        except Exception as e:
            logger.warning(f"Error calculating days to expiry: {e}")
            return 30  # Default fallback
    
    def _calculate_liquidity_score(self, market: Dict[str, Any]) -> float:
        """Calculate a simple liquidity score based on volume and spread."""
        try:
            volume = float(market.get("volume", 0))
            yes_spread = float(market.get("yes_ask", 0)) - float(market.get("yes_bid", 0))
            no_spread = float(market.get("no_ask", 0)) - float(market.get("no_bid", 0))
            avg_spread = (yes_spread + no_spread) / 2
            
            # Higher volume and lower spread = better liquidity
            # Normalize volume (log scale) and invert spread
            volume_score = min(10, max(0, (volume / 1000) ** 0.5))  # Log scale, cap at 10
            spread_score = max(0, 10 - (avg_spread * 100))  # Lower spread = higher score
            
            return (volume_score + spread_score) / 2
            
        except Exception:
            return 5.0  # Default middle score
