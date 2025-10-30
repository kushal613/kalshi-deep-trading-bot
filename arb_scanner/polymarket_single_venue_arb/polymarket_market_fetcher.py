"""
Polymarket market fetcher for arbitrage scanning.
"""
import asyncio
import httpx
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from loguru import logger
from config import load_config


class PolymarketMarketFetcher:
    """Fetches active Polymarket markets and their price data."""
    
    def __init__(self, config):
        self.config = config
        self.http_client = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def initialize(self):
        """Initialize the HTTP client."""
        self.http_client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=30.0
        )
        logger.info("Initialized Polymarket market fetcher")
    
    async def close(self):
        """Close the HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
    
    async def fetch_markets_direct(self) -> List[Dict[str, Any]]:
        """Fetch all active Polymarket markets with price data."""
        logger.info("Fetching Polymarket markets...")
        
        all_markets = []
        page = 0
        limit = 100
        
        while True:
            try:
                logger.info(f"Fetching markets page {page + 1}...")
                
                # Try multiple Polymarket API endpoints
                markets = await self._fetch_markets_page(page, limit)
                
                if not markets:
                    logger.info(f"No more markets found on page {page + 1}")
                    break
                
                # Process and filter markets
                processed_markets = []
                for market in markets:
                    processed_market = self._process_market_data(market)
                    if processed_market:
                        processed_markets.append(processed_market)
                
                all_markets.extend(processed_markets)
                logger.info(f"Page {page + 1}: {len(processed_markets)} markets (total: {len(all_markets)})")
                
                # If we got fewer markets than requested, we've reached the end
                if len(markets) < limit:
                    break
                
                page += 1
                
                # Brief pause to avoid rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error fetching markets page {page + 1}: {e}")
                break
        
        logger.info(f"Fetched {len(all_markets)} active markets with price data")
        return all_markets
    
    async def _fetch_markets_page(self, page: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch a single page of markets from Polymarket API."""
        # Try multiple endpoints
        endpoints = [
            f"https://gamma-api.polymarket.com/events?order=id&ascending=false&closed=false&limit={limit}&offset={page * limit}",
            f"https://gamma-api.polymarket.com/markets?limit={limit}&offset={page * limit}",
            f"https://gamma-api.polymarket.com/events?limit={limit}&offset={page * limit}"
        ]
        
        for endpoint in endpoints:
            try:
                logger.debug(f"Trying endpoint: {endpoint}")
                response = await self.http_client.get(endpoint)
                response.raise_for_status()
                
                data = response.json()
                
                # Handle different response formats
                if isinstance(data, list):
                    markets = data
                elif isinstance(data, dict):
                    markets = data.get("data", []) or data.get("markets", []) or data.get("events", [])
                else:
                    continue
                
                if markets and len(markets) > 0:
                    logger.debug(f"Successfully fetched {len(markets)} markets from {endpoint}")
                    return markets
                    
            except Exception as e:
                logger.debug(f"Failed to fetch from {endpoint}: {e}")
                continue
        
        # If all endpoints fail, try GraphQL
        return await self._fetch_markets_graphql(page, limit)
    
    async def _fetch_markets_graphql(self, page: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch markets using The Graph Protocol (Polymarket's official data source)."""
        try:
            query = """
            query GetMarkets($first: Int!, $skip: Int!) {
                markets(
                    first: $first, 
                    skip: $skip,
                    orderBy: volume, 
                    orderDirection: desc,
                    where: { 
                        volume_gt: "1000000000000000000",
                        active: true 
                    }
                ) {
                    id
                    question
                    description
                    endDate
                    volume
                    liquidity
                    active
                    outcomes
                    outcomePrices
                    tokens {
                        id
                        outcome
                        price
                        volume
                    }
                }
            }
            """
            
            payload = {
                "query": query,
                "variables": {
                    "first": min(limit, 100),  # GraphQL limit
                    "skip": page * limit
                }
            }
            
            # Try multiple GraphQL endpoints
            endpoints = [
                "https://api.thegraph.com/subgraphs/name/polymarket/polymarket",
                "https://gateway.thegraph.com/api/subgraphs/id/QmY3Bf1F5Hf8S3vDxW2Y1K9L8M7N6P5Q4R3S2T1U0V9W8X7Y6Z5"
            ]
            
            for endpoint in endpoints:
                try:
                    response = await self.http_client.post(endpoint, json=payload)
                    response.raise_for_status()
                    
                    data = response.json()
                    if "errors" in data:
                        logger.warning(f"GraphQL errors: {data['errors']}")
                        continue
                        
                    markets = data.get("data", {}).get("markets", [])
                    if markets:
                        logger.debug(f"Successfully fetched {len(markets)} markets from GraphQL")
                        return markets
                        
                except Exception as e:
                    logger.debug(f"Failed to fetch from GraphQL {endpoint}: {e}")
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching markets via GraphQL: {e}")
            return []
    
    def _process_market_data(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process raw market data and extract price information."""
        try:
            # Extract basic market info
            market_id = market.get("id", "")
            question = market.get("question", "")
            description = market.get("description", "")
            end_date = market.get("endDate", "")
            volume = float(market.get("volume", 0))
            liquidity = float(market.get("liquidity", 0))
            active = market.get("active", True)
            
            # Check if market is active
            if not active:
                return None
            
            # Check if market has ended
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if end_dt <= datetime.now(timezone.utc):
                        return None
                except:
                    pass
            
            # Extract outcomes and prices
            outcomes = self._extract_outcomes(market)
            if not outcomes or len(outcomes) < 2:
                return None
            
            # Find YES and NO outcomes
            yes_outcome = None
            no_outcome = None
            
            for outcome in outcomes:
                name = outcome.get("name", "").upper()
                if name in ["YES", "UP"]:
                    yes_outcome = outcome
                elif name in ["NO", "DOWN"]:
                    no_outcome = outcome
            
            if not yes_outcome or not no_outcome:
                return None
            
            # Extract prices (Polymarket uses 0-1 range)
            yes_price = float(yes_outcome.get("price", 0))
            no_price = float(no_outcome.get("price", 0))
            
            # Validate prices
            if not (0 < yes_price < 1 and 0 < no_price < 1):
                return None
            
            # Calculate mid prices (same as individual prices for Polymarket)
            yes_mid = yes_price
            no_mid = no_price
            
            # Calculate days to expiry
            days_to_expiry = self._calculate_days_to_expiry(end_date)
            
            return {
                "market_id": market_id,
                "question": question,
                "description": description,
                "end_date": end_date,
                "volume": volume,
                "liquidity": liquidity,
                "active": active,
                "yes_bid": yes_mid,  # Polymarket doesn't have separate bid/ask
                "no_bid": no_mid,
                "yes_ask": yes_mid,
                "no_ask": no_mid,
                "yes_price": yes_mid,
                "no_price": no_mid,
                "days_to_expiry": days_to_expiry,
                "outcomes": outcomes,
                "raw_data": market
            }
            
        except Exception as e:
            logger.warning(f"Error processing market data: {e}")
            return None
    
    def _extract_outcomes(self, market: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract outcomes from market data."""
        outcomes = []
        
        # Handle different outcome formats
        if "outcomes" in market and "outcomePrices" in market:
            try:
                # Parse JSON strings
                outcomes_list = json.loads(market["outcomes"]) if isinstance(market["outcomes"], str) else market["outcomes"]
                prices_list = json.loads(market["outcomePrices"]) if isinstance(market["outcomePrices"], str) else market["outcomePrices"]
                
                for i, outcome_name in enumerate(outcomes_list):
                    price = float(prices_list[i]) if i < len(prices_list) else 0.5
                    outcomes.append({
                        "name": outcome_name,
                        "price": price
                    })
            except (json.JSONDecodeError, TypeError, IndexError):
                # Fallback to default
                outcomes = [
                    {"name": "YES", "price": 0.5},
                    {"name": "NO", "price": 0.5}
                ]
        elif "outcomes" in market and isinstance(market["outcomes"], list):
            # Handle array format
            for outcome in market["outcomes"]:
                outcomes.append({
                    "name": outcome.get("name", ""),
                    "price": float(outcome.get("price", 0))
                })
        elif "tokens" in market:
            # Handle tokens format
            for token in market["tokens"]:
                outcomes.append({
                    "name": token.get("outcome", ""),
                    "price": float(token.get("price", 0))
                })
        else:
            # Default binary outcomes
            outcomes = [
                {"name": "YES", "price": 0.5},
                {"name": "NO", "price": 0.5}
            ]
        
        return outcomes
    
    def _calculate_days_to_expiry(self, end_date: str) -> int:
        """Calculate days until market expiry."""
        try:
            if not end_date:
                return 30  # Default fallback
            
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = end_dt - now
            days = max(1, delta.days)  # At least 1 day
            return days
            
        except Exception as e:
            logger.warning(f"Error calculating days to expiry: {e}")
            return 30  # Default fallback
