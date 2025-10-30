"""
Polymarket arbitrage calculator for detecting arbitrage opportunities.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from loguru import logger


@dataclass
class PolymarketArbitrageOpportunity:
    """Represents a Polymarket arbitrage opportunity."""
    market_id: str
    question: str
    description: str
    end_date: str
    days_to_expiry: int
    yes_bid: float
    no_bid: float
    yes_ask: float
    no_ask: float
    yes_price: float
    no_price: float
    total_price: float
    edge: float
    opportunity_type: str  # "buy_both" or "sell_both"
    capital_required: float
    profit: float
    roi_percent: float
    annualized_roi_percent: float
    min_spread: float
    liquidity_score: float
    volume: float
    liquidity: float


class PolymarketArbitrageCalculator:
    """Calculates arbitrage opportunities for Polymarket markets."""
    
    def __init__(self, position_size: float = 100.0, fees: float = 0.01, gas: float = 0.02):
        """
        Initialize the calculator.
        
        Args:
            position_size: Size of position to calculate for (in USD)
            fees: Trading fees as decimal (e.g., 0.01 = 1%)
            gas: Gas costs as decimal (e.g., 0.02 = 2%)
        """
        self.position_size = position_size
        self.fees = fees
        self.gas = gas
        self.min_edge_threshold = fees + gas
        
    def calculate_opportunities(self, markets: List[Dict[str, Any]]) -> List[PolymarketArbitrageOpportunity]:
        """
        Calculate arbitrage opportunities from a list of markets.
        
        Args:
            markets: List of market dictionaries with price data
            
        Returns:
            List of arbitrage opportunities
        """
        opportunities = []
        
        for market in markets:
            try:
                opportunity = self._analyze_market(market)
                if opportunity:
                    opportunities.append(opportunity)
            except Exception as e:
                logger.warning(f"Error analyzing market {market.get('market_id', 'unknown')}: {e}")
                continue
        
        # Sort by ROI percentage (descending)
        opportunities.sort(key=lambda x: x.roi_percent, reverse=True)
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        return opportunities
    
    def _analyze_market(self, market: Dict[str, Any]) -> Optional[PolymarketArbitrageOpportunity]:
        """
        Analyze a single market for arbitrage opportunities.
        
        Args:
            market: Market dictionary with price data
            
        Returns:
            PolymarketArbitrageOpportunity object or None if no opportunity
        """
        # Extract price data (Polymarket uses 0-1 range directly)
        yes_bid = float(market.get("yes_bid", 0))
        no_bid = float(market.get("no_bid", 0))
        yes_ask = float(market.get("yes_ask", 0))
        no_ask = float(market.get("no_ask", 0))
        
        # Validate price data
        if not all([0 < yes_bid < 1, 0 < no_bid < 1, 0 < yes_ask < 1, 0 < no_ask < 1]):
            return None
        
        # Compute buy-both using asks and sell-both using bids
        buy_total = yes_ask + no_ask
        buy_edge = 1.0 - buy_total
        
        sell_total = yes_bid + no_bid
        sell_edge = 1.0 - sell_total
        
        chosen = None
        if buy_edge > 0 and buy_edge >= self.min_edge_threshold:
            chosen = ("buy_both", buy_total, buy_edge)
        if sell_edge < 0 and abs(sell_edge) >= self.min_edge_threshold:
            if chosen is None or abs(sell_edge) > abs(chosen[2]):
                chosen = ("sell_both", sell_total, sell_edge)
        if chosen is None:
            return None
        opportunity_type, total_price, edge = chosen
        
        # Mid prices for reporting
        yes_price = (yes_bid + yes_ask) / 2
        no_price = (no_bid + no_ask) / 2
        
        # Calculate financial metrics
        capital_required = total_price * self.position_size
        profit = abs(edge) * self.position_size
        roi_percent = (abs(edge) / total_price) * 100 if total_price > 0 else 0
        
        # Calculate annualized ROI
        days_to_expiry = market.get("days_to_expiry", 30)
        annualized_roi_percent = roi_percent * (365 / days_to_expiry) if days_to_expiry > 0 else roi_percent
        
        # Calculate risk metrics
        min_spread = min(yes_ask - yes_bid, no_ask - no_bid)
        liquidity_score = self._calculate_liquidity_score(market)
        
        return PolymarketArbitrageOpportunity(
            market_id=market.get("market_id", ""),
            question=market.get("question", ""),
            description=market.get("description", ""),
            end_date=market.get("end_date", ""),
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
            liquidity_score=liquidity_score,
            volume=market.get("volume", 0),
            liquidity=market.get("liquidity", 0)
        )
    
    def _calculate_liquidity_score(self, market: Dict[str, Any]) -> float:
        """Calculate a simple liquidity score based on volume and spread."""
        try:
            volume = float(market.get("volume", 0))
            # Polymarket uses 0-1 range, so spread is already in decimal
            yes_spread = float(market.get("yes_ask", 0)) - float(market.get("yes_bid", 0))
            no_spread = float(market.get("no_ask", 0)) - float(market.get("no_bid", 0))
            avg_spread = (yes_spread + no_spread) / 2
            
            # Higher volume and lower spread = better liquidity
            # Normalize volume (log scale) and invert spread
            volume_score = min(10, max(0, (volume / 1000) ** 0.5))  # Log scale, cap at 10
            spread_score = max(0, 10 - (avg_spread * 100))  # Lower spread = higher score
            
            # Combine scores
            liquidity_score = (volume_score + spread_score) / 2
            return liquidity_score
            
        except Exception as e:
            logger.warning(f"Error calculating liquidity score: {e}")
            return 0.0
