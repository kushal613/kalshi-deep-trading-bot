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
                # Best-effort: enrich a subset with live quotes to get real bids/asks
                try:
                    await self._attach_live_quotes(processed_markets[: min(50, len(processed_markets))])
                except Exception:
                    pass
                
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

    async def _attach_live_quotes(self, markets: List[Dict[str, Any]]) -> None:
        """Attach best bid/ask for YES and derive NO via parity, best-effort."""
        if not markets:
            return
        sem = asyncio.Semaphore(10)
        async def fetch_one(m: Dict[str, Any]):
            market_id = m.get("market_id")
            if not market_id:
                return
            endpoints = [
                f"https://clob.polymarket.com/book?market={market_id}",
                f"https://clob.polymarket.com/markets/{market_id}/book",
                f"https://clob.polymarket.com/prices?market={market_id}",
            ]
            best_bid = None
            best_ask = None
            async with sem:
                for url in endpoints:
                    try:
                        resp = await self.http_client.get(url)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                        # Try common book schema
                        if isinstance(data, dict):
                            bids = data.get("bids") or []
                            asks = data.get("asks") or []
                            if bids:
                                try:
                                    best_bid = max(float(b.get("price", 0)) for b in bids)
                                except Exception:
                                    pass
                            if asks:
                                try:
                                    best_ask = min(float(a.get("price", 1)) for a in asks if a.get("price") is not None)
                                except Exception:
                                    pass
                            if best_bid is None and "prices" in data:
                                p = data.get("prices", {})
                                y = p.get("YES") or p.get("Up")
                                if isinstance(y, dict):
                                    try:
                                        best_bid = float(y.get("bid", 0)) or best_bid
                                        best_ask = float(y.get("ask", 0)) or best_ask
                                    except Exception:
                                        pass
                        elif isinstance(data, list) and data:
                            # List of orders
                            bids = [float(x.get("price", 0)) for x in data if str(x.get("side", "")).lower() == "bid"]
                            asks = [float(x.get("price", 0)) for x in data if str(x.get("side", "")).lower() == "ask"]
                            if bids:
                                best_bid = max(bids)
                            if asks:
                                best_ask = min(asks)
                        if best_bid is not None or best_ask is not None:
                            break
                    except Exception:
                        continue
            # Update market dict
            if best_bid is not None and 0 < best_bid < 1:
                m["yes_bid"] = best_bid
            if best_ask is not None and 0 < best_ask < 1:
                m["yes_ask"] = best_ask
            # Derive NO side from parity
            yb = m.get("yes_bid")
            ya = m.get("yes_ask")
            if isinstance(yb, (int, float)) and isinstance(ya, (int, float)):
                m["no_bid"] = max(0.0, min(1.0, 1.0 - ya))
                m["no_ask"] = max(0.0, min(1.0, 1.0 - yb))
        await asyncio.gather(*(fetch_one(m) for m in markets), return_exceptions=True)
    
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
            
            # Mid prices (from outcomes)
            yes_mid = yes_price
            no_mid = no_price

            # Use best bid/ask for YES if available; derive NO from parity
            raw_best_bid = market.get("bestBid")
            raw_best_ask = market.get("bestAsk")
            def _safe_float(x):
                try:
                    return float(x)
                except Exception:
                    return None
            best_bid = _safe_float(raw_best_bid)
            best_ask = _safe_float(raw_best_ask)
            if best_bid is not None and 0 < best_bid < 1:
                yes_bid = best_bid
            else:
                yes_bid = yes_mid
            if best_ask is not None and 0 < best_ask < 1:
                yes_ask = best_ask
            else:
                yes_ask = yes_mid
            # Binary parity to approximate NO side
            no_bid = max(0.0, min(1.0, 1.0 - yes_ask))
            no_ask = max(0.0, min(1.0, 1.0 - yes_bid))
            
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
                "yes_bid": yes_bid,
                "no_bid": no_bid,
                "yes_ask": yes_ask,
                "no_ask": no_ask,
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
