"""
Market data fetcher for Kalshi arbitrage scanner.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from loguru import logger
import httpx
from pathlib import Path
import sys

# Add parent directory to path to import kalshi_client
sys.path.append(str(Path(__file__).parent.parent))
from kalshi_client import KalshiClient
from config import KalshiConfig


class MarketFetcher:
    """Fetches market data from Kalshi API for arbitrage analysis."""
    
    def __init__(self, config: KalshiConfig):
        self.config = config
        self.client = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = KalshiClient(self.config)
        await self.client.login()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.close()
    
    async def fetch_all_active_markets(self) -> List[Dict[str, Any]]:
        """
        Fetch all active markets with their current prices.
        
        Returns:
            List of market dictionaries with price data
        """
        try:
            # Get all events first
            events = await self.client.get_events(limit=1000)  # Get many events
            logger.info(f"Found {len(events)} events")
            
            all_markets = []
            
            # Collect all markets from all events
            for event in events:
                markets = event.get("markets", [])
                for market in markets:
                    # Get detailed market data with prices
                    market_ticker = market.get("ticker")
                    if market_ticker:
                        detailed_market = await self.client.get_market_with_odds(market_ticker)
                        if detailed_market and detailed_market.get("status") == "open":
                            # Add event context
                            detailed_market["event_ticker"] = event.get("event_ticker", "")
                            detailed_market["event_title"] = event.get("title", "")
                            detailed_market["category"] = event.get("category", "")
                            detailed_market["strike_date"] = event.get("strike_date", "")
                            
                            all_markets.append(detailed_market)
            
            logger.info(f"Fetched {len(all_markets)} active markets with price data")
            return all_markets
            
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    async def fetch_markets_direct(self) -> List[Dict[str, Any]]:
        """
        Alternative method: fetch markets directly without going through events.
        This might be more efficient for getting all markets at once.
        """
        try:
            if not self.client:
                raise ValueError("Client not initialized")
                
            # Use the client's internal method to get headers
            headers = await self.client._get_headers("GET", "/trade-api/v2/markets")
            
            all_markets = []
            cursor = None
            page = 1
            
            while True:
                try:
                    params = {
                        "limit": 100,  # Maximum markets per page
                        "status": "open"  # Only get open markets
                    }
                    
                    if cursor:
                        params["cursor"] = cursor
                    
                    logger.info(f"Fetching markets page {page}...")
                    response = await self.client.client.get(
                        "/trade-api/v2/markets",
                        headers=headers,
                        params=params
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    if data is None:
                        logger.error("Received None response from API")
                        break
                        
                    markets = data.get("markets", []) if isinstance(data, dict) else []
                    
                    if not markets:
                        break
                    
                    # Filter for markets with valid price data
                    for market in markets:
                        if (market.get("yes_bid", 0) > 0 and market.get("no_bid", 0) > 0 and
                            market.get("yes_ask", 0) > 0 and market.get("no_ask", 0) > 0):
                            all_markets.append(market)
                    
                    logger.info(f"Page {page}: {len(markets)} markets (total: {len(all_markets)})")
                    
                    # Check if there's a next page
                    cursor = data.get("cursor")
                    if not cursor:
                        break
                    
                    page += 1
                    
                except Exception as e:
                    logger.error(f"Error fetching markets page {page}: {e}")
                    break
            
            logger.info(f"Fetched {len(all_markets)} active markets with price data")
            return all_markets
            
        except Exception as e:
            logger.error(f"Error fetching markets directly: {e}")
            return []
